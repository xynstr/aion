def register(api):
    import threading
    import time
    import datetime
    import os
    
    # Sende alle X Sekunden einen Heartbeat (Standard: 60 Sekunden)
    interval = 60
    running = True
    heartbeat_log = os.path.join(os.path.dirname(__file__), 'heartbeat.log')
    
    def heartbeat():
        while running:
            timestamp = datetime.datetime.now().isoformat()
            with open(heartbeat_log, 'a', encoding='utf-8') as f:
                f.write(f"Heartbeat: {timestamp}\n")
            time.sleep(interval)
    
    t = threading.Thread(target=heartbeat, daemon=True)
    t.start()
    
    def get_last_heartbeat(input: dict):
        try:
            with open(heartbeat_log, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            last = [l for l in lines if l.startswith("Heartbeat:")][-1]
            return {"last_heartbeat": last.strip()}
        except Exception as e:
            return {"error": str(e)}
    
    api.register_tool(
        name="heartbeat_last",
        description="Gibt den Zeitstempel des letzten Heartbeats zurcck.",
        func=get_last_heartbeat,
        input_schema={"type": "object", "properties": {}}
    )