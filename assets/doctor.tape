# skeval doctor — check a harness against the prerequisites.
Output assets/doctor.gif

Require uv

Set Shell "bash"
Set FontSize 17
Set Width 1500
Set Height 430
Set Padding 24
Set Theme "Catppuccin Mocha"
Set WindowBar Colorful
Set TypingSpeed 55ms
Set WaitTimeout 180s

Hide
Type "cd /Users/jasperginn/Documents/code_projects/agents/skills-cicd" Enter
Type "export PS1='$ ' && export COLUMNS=140 && clear" Enter
Show

Sleep 800ms
Type "uv run skeval doctor" Sleep 600ms Enter
Wait+Screen /qualifies/
Sleep 400ms
Screenshot assets/.doctor-check.png
Sleep 2500ms
