# Third-party notices

Otto includes ideas and small adapted pieces from the projects below. Each is used under its own licence.

## Nus Companion (nus-desktop)

- Source: https://github.com/potlakai/nus-desktop (studied at commit 592e30f, 27 October 2026)
- Licence: MIT. Copyright (c) 2026 Pranav Desu
- What Otto uses:
  - `core/sensitive.py`: the list of private-field words is adapted from `companion/src/guide/sensitive.js`.
  - `hands/ui_probe.py`: the name-matching scores (`name_score`) and the "smallest control under a point"
    rule are ported from `companion/src/win/probe.ps1`. The overall approach (a bounded list of interactive,
    on-screen controls from Windows UI Automation) follows that file; the code itself is new Python.
- No Nus branding, mascot ("Knot"), prompts, models or training data are used.

Full licence text:

```
MIT License

Copyright (c) 2026 Pranav Desu

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
