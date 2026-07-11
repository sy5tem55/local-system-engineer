import shutil

p = '/mnt/c/Users/SY5/Claude/Projects/Goethe_GUI/goethe-gui.ps1'
bak = '/mnt/c/Users/SY5/Claude/Projects/Goethe_GUI/backups/goethe-gui.ps1.bak-20260711-pre-pidfile'
shutil.copy2(p, bak)
print('backup:', bak)

data = open(p, 'rb').read()
old = b'"sleep 1 && pgrep -f \'goethe.py\' | head -1 > \'$script:WslScriptDir/$ChildPidFile\' 2>/dev/null &",'
new = b'"( for i in `$(seq 1 20); do [ -s /tmp/goethe-gateway.pid ] && break; sleep 0.5; done; cat /tmp/goethe-gateway.pid > \'$script:WslScriptDir/$ChildPidFile\' 2>/dev/null ) &",'
n = data.count(old)
print('occurrences of target line:', n)
if n == 1:
    open(p, 'wb').write(data.replace(old, new))
    print('PATCHED OK')
else:
    print('ABORT - expected exactly 1 occurrence, file untouched')
