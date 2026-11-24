# Third-party notices

## Laravel framework

Titanspan's Support API inventory and selected behavior are informed by
Laravel framework `v13.44.1`, commit
`8a8c4a84852869e13190d89f9da873cd9a70f14c`:

<https://github.com/laravel/framework/tree/8a8c4a84852869e13190d89f9da873cd9a70f14c>

Laravel framework is distributed under the MIT License. Titanspan is an
independent project and is not affiliated with or endorsed by Laravel. The
current Python Support implementation is written for Titanspan; this notice
preserves attribution for the upstream API and behavior reference. Future
adaptations of upstream source or tests must retain applicable notices.
Sleep compatibility tests translate behavior from Laravel's upstream test
suite; the pinned source and test paths are listed in the compatibility
inventory. Environment compatibility cases translate the environment helper
and bootstrap expectations from Laravel's Support and Foundation test suites.
Retry helper behavior follows the pinned Support helper implementation; its
test evidence is listed in the compatibility inventory.

Copyright (c) Taylor Otwell

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

## AnyIO

Titanspan uses AnyIO for backend-neutral asynchronous waiting in the Support
timebox and Sleep utilities. Titanspan does not adapt or redistribute AnyIO
source code.

AnyIO 4.16.0 is distributed under the MIT License. Copyright (c) 2018 Alex
Grönholm. See the [official AnyIO 4.16.0 license](https://github.com/agronholm/anyio/blob/4.16.0/LICENSE)
for the complete notice.

## Babel

The optional `numbers` extra uses Babel 2.19.0's public locale formatting
and parsing APIs. Titanspan does not copy Babel source. Babel is distributed
under the BSD 3-Clause License; see the
[Babel 2.19.0 license](https://github.com/python-babel/babel/blob/v2.19.0/LICENSE).

## num2words

The optional `numbers` extra uses the public `num2words` function from
num2words 0.5.14. Titanspan does not copy num2words source. The upstream
package is distributed under LGPL-2.1; see the
[0.5.14 release metadata](https://pypi.org/project/num2words/0.5.14/) and
[upstream license text](https://raw.githubusercontent.com/savoirfairelinux/num2words/6abe2c6/COPYING).

## Tenacity

Titanspan delegates bounded retry execution to Tenacity 9.2.1. No Tenacity
source code is copied into Titanspan. Tenacity is distributed under the
Apache License 2.0; see the [official Tenacity 9.2.1 license](https://github.com/jd/tenacity/blob/9.2.1/LICENSE).
