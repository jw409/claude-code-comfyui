#!/usr/bin/env python3
"""
Multi-Agent Observability Server - Python Implementation
Replaces the Bun/TypeScript server with pure Python
"""

import json
import sqlite3
import asyncio
import websockets
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Set, Optional
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Database path
DB_PATH = Path(__file__).parent / "observability.db"

# WebSocket clients
ws_clients: Set[websockets.WebSocketServerProtocol] = set()

class ObservabilityDB:
    """Handle all database operations"""
    
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Initialize the SQLite database with required tables"""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        # Create events table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_app TEXT NOT NULL,
                session_id TEXT NOT NULL,
                hook_event_type TEXT NOT NULL,
                tool_name TEXT,
                payload TEXT NOT NULL,
                summary TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                metadata TEXT
            )
        """)
        
        # Create indexes for better query performance
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_session ON events(session_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_source ON events(source_app)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON events(timestamp)")
        
        conn.commit()
        conn.close()
        logger.info(f"Database initialized at {self.db_path}")
    
    def insert_event(self, event: Dict) -> int:
        """Insert a new event into the database"""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO events (source_app, session_id, hook_event_type, tool_name, payload, summary, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            event.get('source_app'),
            event.get('session_id'),
            event.get('hook_event_type'),
            event.get('tool_name'),
            json.dumps(event.get('payload', {})),
            event.get('summary'),
            json.dumps(event.get('metadata', {}))
        ))
        
        event_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return event_id
    
    def get_recent_events(self, limit: int = 100, session_id: Optional[str] = None) -> List[Dict]:
        """Get recent events from the database"""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        if session_id:
            cursor.execute("""
                SELECT * FROM events 
                WHERE session_id = ?
                ORDER BY timestamp DESC 
                LIMIT ?
            """, (session_id, limit))
        else:
            cursor.execute("""
                SELECT * FROM events 
                ORDER BY timestamp DESC 
                LIMIT ?
            """, (limit,))
        
        rows = cursor.fetchall()
        conn.close()
        
        events = []
        for row in rows:
            event = dict(row)
            # Parse JSON fields
            if event.get('payload'):
                event['payload'] = json.loads(event['payload'])
            if event.get('metadata'):
                event['metadata'] = json.loads(event['metadata'])
            events.append(event)
        
        return events
    
    def get_filter_options(self) -> Dict:
        """Get available filter options from the database"""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        # Get unique source apps
        cursor.execute("SELECT DISTINCT source_app FROM events WHERE source_app IS NOT NULL")
        source_apps = [row[0] for row in cursor.fetchall()]
        
        # Get unique session IDs
        cursor.execute("SELECT DISTINCT session_id FROM events WHERE session_id IS NOT NULL ORDER BY session_id DESC LIMIT 20")
        session_ids = [row[0] for row in cursor.fetchall()]
        
        # Get unique event types
        cursor.execute("SELECT DISTINCT hook_event_type FROM events WHERE hook_event_type IS NOT NULL")
        event_types = [row[0] for row in cursor.fetchall()]
        
        # Get unique tool names
        cursor.execute("SELECT DISTINCT tool_name FROM events WHERE tool_name IS NOT NULL")
        tool_names = [row[0] for row in cursor.fetchall()]
        
        conn.close()
        
        return {
            'source_apps': source_apps,
            'session_ids': session_ids,
            'event_types': event_types,
            'tool_names': tool_names
        }

# Global database instance
db = ObservabilityDB(DB_PATH)

class ObservabilityHTTPHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the observability server"""
    
    def do_OPTIONS(self):
        """Handle CORS preflight requests"""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
    
    def do_POST(self):
        """Handle POST requests"""
        if self.path == '/events':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            
            try:
                event = json.loads(post_data.decode('utf-8'))
                
                # Validate required fields
                required_fields = ['source_app', 'session_id', 'hook_event_type', 'payload']
                if not all(field in event for field in required_fields):
                    self.send_error(400, 'Missing required fields')
                    return
                
                # Insert event into database
                event_id = db.insert_event(event)
                event['id'] = event_id
                event['timestamp'] = datetime.now().isoformat()
                
                # Broadcast to WebSocket clients
                asyncio.run(broadcast_event(event))
                
                # Send response
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps({'success': True, 'event_id': event_id}).encode())
                
                logger.info(f"Event received: {event.get('hook_event_type')} from {event.get('source_app')}")
                
            except json.JSONDecodeError:
                self.send_error(400, 'Invalid JSON')
            except Exception as e:
                logger.error(f"Error processing event: {e}")
                self.send_error(500, str(e))
    
    def do_GET(self):
        """Handle GET requests"""
        if self.path == '/health':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({'status': 'healthy', 'ws_clients': len(ws_clients)}).encode())
            
        elif self.path == '/events/filter-options':
            options = db.get_filter_options()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(options).encode())
            
        elif self.path.startswith('/events'):
            # Parse query parameters
            from urllib.parse import urlparse, parse_qs
            parsed_url = urlparse(self.path)
            query_params = parse_qs(parsed_url.query)
            
            limit = int(query_params.get('limit', [100])[0])
            session_id = query_params.get('session_id', [None])[0]
            
            events = db.get_recent_events(limit, session_id)
            
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(events).encode())
        else:
            self.send_error(404, 'Not Found')
    
    def log_message(self, format, *args):
        """Suppress default logging"""
        pass

async def broadcast_event(event: Dict):
    """Broadcast event to all connected WebSocket clients"""
    if ws_clients:
        message = json.dumps(event)
        disconnected = set()
        for client in ws_clients:
            try:
                await client.send(message)
            except:
                disconnected.add(client)
        # Remove disconnected clients
        for client in disconnected:
            ws_clients.discard(client)

async def websocket_handler(websocket, path):
    """Handle WebSocket connections"""
    ws_clients.add(websocket)
    logger.info(f"WebSocket client connected. Total clients: {len(ws_clients)}")
    
    try:
        # Send initial data
        events = db.get_recent_events(50)
        await websocket.send(json.dumps({
            'type': 'initial',
            'events': events
        }))
        
        # Keep connection alive
        async for message in websocket:
            # Handle ping/pong or other messages if needed
            pass
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        ws_clients.discard(websocket)
        logger.info(f"WebSocket client disconnected. Total clients: {len(ws_clients)}")

def run_http_server():
    """Run the HTTP server in a separate thread"""
    server = HTTPServer(('0.0.0.0', 4000), ObservabilityHTTPHandler)
    logger.info("HTTP server started on port 4000")
    server.serve_forever()

async def main():
    """Main async function to run both HTTP and WebSocket servers"""
    # Start HTTP server in a thread
    http_thread = threading.Thread(target=run_http_server, daemon=True)
    http_thread.start()
    
    # Start WebSocket server
    async with websockets.serve(websocket_handler, '0.0.0.0', 4001):
        logger.info("WebSocket server started on port 4001")
        logger.info("=" * 50)
        logger.info("Multi-Agent Observability Server Running")
        logger.info("HTTP API: http://localhost:4000")
        logger.info("WebSocket: ws://localhost:4001")
        logger.info("=" * 50)
        await asyncio.Future()  # Run forever

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Server shutting down...")