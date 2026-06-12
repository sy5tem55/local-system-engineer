# launcher-script-location.md

The launcher script lives in the Windows git repo, accessible from WSL at:
  /mnt/c/Users/SY5/Documents/Claude/Projects/local-system-engineer/

When editing or creating a new launcher version (e.g. lse-stack-launch-1.064.ps1),
write the file to that path directly — NOT to /opt/local-se/.

After writing, remind the user to run:
  cd C:\Users\SY5\Documents\Claude\Projects\local-system-engineer
  .\certsign.ps1 -Target lse-stack-launch-X.XXX.ps1
  git add lse-stack-launch-X.XXX.ps1
  git commit -m "feat: launcher vX.XXX — <what changed>"