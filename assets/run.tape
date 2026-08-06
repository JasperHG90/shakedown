# skeval run — the conformance matrix over a real skill.
Output assets/run.gif

Require uv

Set Shell "bash"
Set FontSize 17
Set Width 1500
Set Height 460
Set Padding 24
Set Theme "Catppuccin Mocha"
Set WindowBar Colorful
Set TypingSpeed 55ms
Set WaitTimeout 300s

Hide
Type "cd /Users/jasperginn/Documents/code_projects/agents/skills-cicd" Enter
Type "export PS1='$ ' && export COLUMNS=140 && clear" Enter
Show

Sleep 800ms
Type "uv run skeval run examples/write-plan -j 4" Sleep 600ms Enter
Wait+Screen /report:/
Sleep 400ms
Screenshot assets/.run-check.png
Sleep 2500ms
