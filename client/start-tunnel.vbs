' hermes-fleet-memory: Silent Windows Launcher
' Launches Desktop Bridge and WSTunnel in the background without command prompt popups.
Set WshShell = CreateObject("WScript.Shell")

' 1. Start Desktop Execution Bridge (Python)
WshShell.Run "python.exe desktop_bridge.py", 0, False

' 2. Start WSTunnel Client (Reverse + Forward)
' Update SERVER_HOST and TUNNEL_KEY below. TUNNEL_KEY is the X-Fleet-Key value in
' the hub Caddyfile. Use a secret of its own, never the Qdrant key: it is visible
' on this process's command line to anything running on the machine.
SERVER_HOST = "brain.yourdomain.com"
TUNNEL_KEY = "your_256bit_tunnel_key"

WshShell.Run "wstunnel.exe client -L tcp://127.0.0.1:6333:127.0.0.1:6333 -R tcp://127.0.0.1:8099:127.0.0.1:8099 --http-headers ""X-Fleet-Key: " & TUNNEL_KEY & """ --websocket-ping-frequency 20s -P tunnel wss://" & SERVER_HOST, 0, False
