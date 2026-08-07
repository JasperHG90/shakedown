# shakedown doctor — check a harness against the prerequisites.
Output assets/doctor.gif

Require uv

Set Shell "bash"
Set FontSize 17
Set Width 1500
Set Height 470
Set Padding 24
Set Theme "Catppuccin Mocha"
Set WindowBar Colorful
Set TypingSpeed 55ms
Set WaitTimeout 180s

Hide
Type "export PS1='$ ' && export COLUMNS=140 && clear" Enter
Show

Sleep 800ms
Type "uv run shakedown doctor --harness claude-code" Sleep 600ms Enter
Wait+Screen /qualifies/
Sleep 400ms
Sleep 2500ms
