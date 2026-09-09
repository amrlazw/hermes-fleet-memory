' hermes-fleet-memory: Silent Windows Launcher
' Launches Desktop Bridge and WSTunnel in the background without command prompt popups.
Set WshShell = CreateObject("WScript.Shell")

' 1. Start Desktop Execution Bridge (Python)
WshShell.Run "python.exe desktop_bridge.py", 0, False

' 2. Start WSTunnel Client (Reverse + Forward)
' Update SERVER_HOST and FLEET_KEY below
SERVER_HOST = "brain.yourdomain.com"
FLEET_KEY = "your_256bit_cluster_secret"

WshShell.Run "wstunnel.exe client -L tcp://127.0.0.1:6333:127.0.0.1:6333 -R tcp://127.0.0.1:8099:127.0.0.1:8099 --http-headers ""X-Fleet-Key: " & FLEET_KEY & """ --websocket-ping-frequency 20s -P tunnel wss://" & SERVER_HOST, 0, False
