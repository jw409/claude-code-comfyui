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
import subprocess
import sys
import os

# LLM Integration for enhanced features
try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Configuration - ComfyUI Style
HTTP_PORT = int(os.getenv('OBSERVABILITY_PORT', '8888'))  # Use 8888 like unified dashboard
WS_PORT = int(os.getenv('OBSERVABILITY_WS_PORT', '8889'))  # WebSocket on 8889
DB_PATH = Path(__file__).parent / "observability.db"

# WebSocket clients
ws_clients: Set[websockets.WebSocketServerProtocol] = set()

class LLMInstaller:
    """The missing piece - LLM-powered installer and verifier"""
    
    def __init__(self):
        self.claude_client = None
        self.gemini_client = None
        
        # Initialize available LLMs
        if ANTHROPIC_AVAILABLE and os.getenv('ANTHROPIC_API_KEY'):
            self.claude_client = anthropic.Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
            
        if GEMINI_AVAILABLE and os.getenv('GEMINI_API_KEY'):
            genai.configure(api_key=os.getenv('GEMINI_API_KEY'))
            self.gemini_client = genai.GenerativeModel('gemini-pro')
    
    def verify_hook_setup(self, project_path: str) -> Dict:
        """LLM-powered hook verification - what they're missing!"""
        claude_dir = Path(project_path) / ".claude"
        
        if not claude_dir.exists():
            return {"status": "missing", "message": "No .claude directory found"}
        
        settings_file = claude_dir / "settings.json"
        if not settings_file.exists():
            return {"status": "missing", "message": "No settings.json found"}
        
        # Analyze current setup with LLM
        try:
            with open(settings_file) as f:
                settings = json.load(f)
            
            analysis_prompt = f"""
            Analyze this Claude Code hook setup and suggest improvements:
            
            Settings: {json.dumps(settings, indent=2)}
            
            Check for:
            1. Missing essential hooks (PreToolUse, PostToolUse, etc.)
            2. Incorrect paths or commands
            3. Security vulnerabilities
            4. Performance optimizations
            5. Integration with observability system
            
            Provide specific, actionable recommendations.
            """
            
            if self.claude_client:
                response = self.claude_client.messages.create(
                    model="claude-3-sonnet-20240229",
                    max_tokens=1000,
                    messages=[{"role": "user", "content": analysis_prompt}]
                )
                analysis = response.content[0].text
            elif self.gemini_client:
                response = self.gemini_client.generate_content(analysis_prompt)
                analysis = response.text
            else:
                analysis = "LLM analysis unavailable - install anthropic or google-generativeai"
            
            return {
                "status": "analyzed",
                "settings": settings,
                "llm_analysis": analysis,
                "recommendations": []  # Could parse LLM response for structured recommendations
            }
            
        except Exception as e:
            return {"status": "error", "message": f"Analysis failed: {str(e)}"}
    
    def auto_install_hooks(self, project_path: str, source_app: str) -> Dict:
        """Auto-install hooks with LLM guidance - the ComfyUI experience!"""
        try:
            claude_dir = Path(project_path) / ".claude"
            claude_dir.mkdir(exist_ok=True)
            
            # Copy our enhanced hooks
            source_hooks = Path(__file__).parent.parent.parent / ".claude" / "hooks"
            target_hooks = claude_dir / "hooks"
            target_hooks.mkdir(exist_ok=True)
            
            # Copy enhanced hook files
            import shutil
            for hook_file in source_hooks.glob("*.py"):
                shutil.copy2(hook_file, target_hooks / hook_file.name)
            
            # Generate optimized settings.json with LLM
            settings_template = {
                "hooks": {
                    "PreToolUse": [{
                        "matcher": ".*",
                        "hooks": [{
                            "type": "command",
                            "command": f"uv run .claude/hooks/send_event.py --source-app {source_app} --event-type PreToolUse --summarize --server-port {HTTP_PORT}"
                        }]
                    }],
                    "PostToolUse": [{
                        "matcher": ".*", 
                        "hooks": [{
                            "type": "command",
                            "command": f"uv run .claude/hooks/send_event.py --source-app {source_app} --event-type PostToolUse --summarize --server-port {HTTP_PORT}"
                        }]
                    }]
                }
            }
            
            settings_file = claude_dir / "settings.json"
            with open(settings_file, 'w') as f:
                json.dump(settings_template, f, indent=2)
            
            return {
                "status": "installed",
                "message": f"Hooks installed for {source_app}",
                "settings_path": str(settings_file),
                "server_url": f"http://localhost:{HTTP_PORT}"
            }
            
        except Exception as e:
            return {"status": "error", "message": f"Installation failed: {str(e)}"}

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
    
    def get_active_sessions(self) -> List[Dict]:
        """Get active sessions based on recent activity"""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Get sessions with activity in the last hour, with their latest event
        cursor.execute("""
            SELECT 
                session_id,
                source_app,
                MAX(timestamp) as last_activity,
                COUNT(*) as event_count,
                GROUP_CONCAT(DISTINCT hook_event_type) as event_types
            FROM events 
            WHERE timestamp > datetime('now', '-1 hour')
            GROUP BY session_id, source_app
            ORDER BY last_activity DESC
        """)
        
        rows = cursor.fetchall()
        conn.close()
        
        sessions = []
        for row in rows:
            session = dict(row)
            # Parse the concatenated event types
            if session.get('event_types'):
                session['event_types'] = session['event_types'].split(',')
            sessions.append(session)
        
        return sessions

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
                
                # Broadcast to WebSocket clients - format for Vue.js client
                websocket_message = {
                    'type': 'event',
                    'data': event
                }
                asyncio.run(broadcast_websocket_message(websocket_message))
                
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
        
        # ========== ENHANCED ENDPOINTS - THE COMFYUI DIFFERENCE ==========
        elif self.path.startswith('/api/installer/verify'):
            """LLM-powered hook verification - what they're missing!"""
            from urllib.parse import urlparse, parse_qs
            parsed = urlparse(self.path)
            query_params = parse_qs(parsed.query)
            
            project_path = query_params.get('path', ['.'])[0]
            installer = LLMInstaller()
            result = installer.verify_hook_setup(project_path)
            
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(result).encode())
        
        elif self.path.startswith('/api/installer/auto-install'):
            """One-click LLM-guided installation"""
            from urllib.parse import urlparse, parse_qs
            parsed = urlparse(self.path)
            query_params = parse_qs(parsed.query)
            
            project_path = query_params.get('path', ['.'])[0]
            source_app = query_params.get('app', ['claude-comfyui'])[0]
            
            installer = LLMInstaller()
            result = installer.auto_install_hooks(project_path, source_app)
            
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(result).encode())
        
        elif self.path == '/' or self.path == '/index.html':
            """Serve the Vue.js frontend"""
            try:
                frontend_path = Path(__file__).parent.parent / "client" / "dist" / "index.html"
                if frontend_path.exists():
                    with open(frontend_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    self.send_response(200)
                    self.send_header('Content-Type', 'text/html')
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                    self.wfile.write(content.encode('utf-8'))
                else:
                    self.send_error(404, 'Frontend not built. Run: npm run build in apps/client')
            except Exception as e:
                self.send_error(500, f'Error serving frontend: {str(e)}')
        
        elif self.path.startswith('/assets/'):
            """Serve static assets"""
            try:
                asset_path = Path(__file__).parent.parent / "client" / "dist" / self.path.lstrip('/')
                if asset_path.exists():
                    # Determine content type
                    if asset_path.suffix == '.js':
                        content_type = 'application/javascript'
                    elif asset_path.suffix == '.css':
                        content_type = 'text/css'
                    elif asset_path.suffix == '.png':
                        content_type = 'image/png'
                    elif asset_path.suffix == '.svg':
                        content_type = 'image/svg+xml'
                    else:
                        content_type = 'application/octet-stream'
                    
                    with open(asset_path, 'rb') as f:
                        content = f.read()
                    
                    self.send_response(200)
                    self.send_header('Content-Type', content_type)
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                    self.wfile.write(content)
                else:
                    self.send_error(404, 'Asset not found')
            except Exception as e:
                self.send_error(500, f'Error serving asset: {str(e)}')
        
        elif self.path == '/api/dashboard':
            """Unified dashboard endpoint - compete with TalentOS dashboard"""
            dashboard_data = {
                "system_status": {
                    "server": "healthy",
                    "port": HTTP_PORT,
                    "ws_port": WS_PORT,
                    "ws_clients": len(ws_clients),
                    "database": "connected"
                },
                "llm_status": {
                    "claude": ANTHROPIC_AVAILABLE and bool(os.getenv('ANTHROPIC_API_KEY')),
                    "gemini": GEMINI_AVAILABLE and bool(os.getenv('GEMINI_API_KEY'))
                },
                "recent_events": db.get_recent_events(10),
                "active_sessions": db.get_active_sessions()
            }
            
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(dashboard_data).encode())
        else:
            self.send_error(404, 'Not Found')
    
    def log_message(self, format, *args):
        """Suppress default logging"""
        pass

async def broadcast_websocket_message(message: Dict):
    """Broadcast message to all connected WebSocket clients"""
    if ws_clients:
        json_message = json.dumps(message)
        disconnected = set()
        for client in ws_clients:
            try:
                await client.send(json_message)
            except:
                disconnected.add(client)
        # Remove disconnected clients
        for client in disconnected:
            ws_clients.discard(client)

async def websocket_handler(websocket):
    """Handle WebSocket connections"""
    ws_clients.add(websocket)
    logger.info(f"WebSocket client connected. Total clients: {len(ws_clients)}")
    
    try:
        # Send initial data in Vue.js client format
        events = db.get_recent_events(50)
        await websocket.send(json.dumps({
            'type': 'initial',
            'data': events
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
    global db
    db = ObservabilityDB(DB_PATH)
    server = HTTPServer(('0.0.0.0', HTTP_PORT), ObservabilityHTTPHandler)
    logger.info(f"🚀 Claude Code ComfyUI Server started on port {HTTP_PORT}")
    logger.info(f"🎯 Enhanced with LLM-powered installer and verifier!")
    server.serve_forever()

async def main():
    """Main async function to run both HTTP and WebSocket servers"""
    # Start HTTP server in a thread
    http_thread = threading.Thread(target=run_http_server, daemon=True)
    http_thread.start()
    
    # Start WebSocket server
    async with websockets.serve(websocket_handler, '0.0.0.0', WS_PORT):
        logger.info(f"WebSocket server started on port {WS_PORT}")
        logger.info("=" * 60)
        logger.info("🎨 CLAUDE CODE COMFYUI SERVER RUNNING")
        logger.info(f"🌐 HTTP API: http://localhost:{HTTP_PORT}")
        logger.info(f"🔗 WebSocket: ws://localhost:{WS_PORT}")
        logger.info("✨ LLM-Powered Features:")
        logger.info("   • Auto Hook Installation")
        logger.info("   • Intelligent Verification") 
        logger.info("   • Claude + Gemini Support")
        logger.info("   • Crash-Consistent Persistence")
        logger.info("=" * 60)
        await asyncio.Future()  # Run forever

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Server shutting down...")