Portrait-3D

2D photo → 3D mesh via Depth Anything V2

cd /home/sy5/projects/portrait-3d && pkill -9 -f uvicorn && sleep 1
backend/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8787 2>&1 | tee /tmp/uvicorn.log &

http://localhost:8787/