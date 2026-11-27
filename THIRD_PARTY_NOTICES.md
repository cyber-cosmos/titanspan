# Third-party notices

## Laravel framework

Titanspan's early API research and selected behavior were informed by Laravel
framework `v13.44.1`, commit
`8a8c4a84852869e13190d89f9da873cd9a70f14c`:

<https://github.com/laravel/framework/tree/8a8c4a84852869e13190d89f9da873cd9a70f14c>

Laravel framework is distributed under the MIT License. Titanspan is an
independent project and is not affiliated with or endorsed by Laravel. The
current APIs follow the native Titanspan specifications; this notice records
historical design provenance and preserves applicable attribution. The pinned
source tree remains available at the link above. Tests under
`tests/unit/support/` contain selected translated behavior cases for sleep,
environment values, and retry helpers. No Laravel Contracts implementation
or literal upstream test source was copied into the Titanspan Contracts
package. These references do not establish API compatibility requirements.

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

## python-dotenv

Titanspan uses python-dotenv 1.2.4 to read dotenv values without mutating
the process environment. No python-dotenv source code is copied into
Titanspan. The package is distributed under the BSD 3-Clause License; see
the [official python-dotenv 1.2.4 license](https://github.com/theskumar/python-dotenv/blob/v1.2.4/LICENSE).

## HTTPX2

Titanspan uses HTTPX2 2.16.2 for synchronous and asynchronous outgoing HTTP
transport, connection pooling, and response streaming. No HTTPX2 source code
is copied into Titanspan. HTTPX2 is distributed under the BSD 3-Clause
License; see the [official HTTPX2 license](https://github.com/pydantic/httpx2/blob/main/LICENSE).

## email-validator

Titanspan installs email-validator 2.4.0 for Pydantic's `EmailStr` schema
support. No email-validator source is copied into Titanspan. The package is
distributed under The Unlicense; see the
[2.4.0 source license](https://github.com/JoshData/python-email-validator/blob/v2.4.0/LICENSE).

## dnspython

email-validator depends on dnspython 2.9.2. Titanspan does not use DNS
deliverability checks for Pydantic `EmailStr` values. dnspython is distributed
under the ISC License; see the
[2.9.2 license](https://github.com/rthalley/dnspython/blob/v2.9.2/LICENSE).

## typing-extensions

Titanspan uses typing-extensions 4.16.0's public `TypeForm` type to express
Pydantic-compatible schemas on supported Python versions. The package is
distributed under the PSF License; see the
[upstream project](https://github.com/python/typing_extensions).

## Cache adapters

Titanspan delegates bounded in-memory expiry and eviction to cachetools
8.0.3. cachetools is distributed under the MIT License; see the
[official cachetools 8.0.3 license](https://github.com/tkem/cachetools/blob/v8.0.3/LICENSE).

The optional `redis` extra uses redis-py 8.2.0 for synchronous and
asynchronous Redis clients. redis-py is distributed under the MIT License;
see the [official redis-py 8.2.0 license](https://github.com/redis/redis-py/blob/v8.2.0/LICENSE).

## python-multipart

Titanspan uses python-multipart 0.0.34 through Starlette's bounded multipart
parser for incoming file uploads. No python-multipart source code is copied
into Titanspan. python-multipart is distributed under the Apache License 2.0;
see the [0.0.34 package metadata](https://github.com/Kludex/python-multipart/blob/0.0.34/pyproject.toml)
and [license text](https://github.com/Kludex/python-multipart/blob/0.0.34/LICENSE.txt).

## Password hashing libraries

Titanspan delegates Argon2id hashing, verification, parameter parsing, and
rehash detection to argon2-cffi 25.1.0, distributed under the MIT License.
See the [official license](https://github.com/hynek/argon2-cffi/blob/main/LICENSE).

argon2-cffi uses argon2-cffi-bindings 26.2.0, also distributed under the MIT
License. The bindings distribution includes the Argon2 reference
implementation under CC0 as described in its upstream README. See the
[bindings license](https://github.com/hynek/argon2-cffi-bindings/blob/main/LICENSE).

argon2-cffi-bindings depends on CFFI 2.1.1 and pycparser 3.12. CFFI is
distributed under the MIT No Attribution License (MIT-0); see its
[official license](https://github.com/python-cffi/cffi/blob/main/LICENSE).
pycparser is distributed under the BSD 3-Clause License; see the
[official license](https://github.com/eliben/pycparser/blob/main/LICENSE).

Titanspan delegates Bcrypt salt generation, hashing, and verification to
bcrypt 5.0.0, distributed under the Apache License 2.0. See the
[official license](https://github.com/pyca/bcrypt/blob/main/LICENSE).

## Database drivers

SQLAlchemy's asyncio extra uses greenlet 3.5.6. Its declared license
expression is `MIT AND PSF-2.0`; the distribution includes both required
license files. See the [release metadata](https://github.com/python-greenlet/greenlet/blob/3.5.6/pyproject.toml),
[MIT license](https://github.com/python-greenlet/greenlet/blob/3.5.6/LICENSE),
and [PSF license](https://github.com/python-greenlet/greenlet/blob/3.5.6/LICENSE.PSF).
Titanspan does not copy greenlet source code.

The optional `postgresql` extra installs Psycopg 3.3.9 and its
`psycopg-binary` 3.3.9 extra. Both distributions declare `LGPL-3.0-only` and
include their license file. See the [Psycopg release metadata](https://github.com/psycopg/psycopg/blob/3.3.9/psycopg/pyproject.toml),
[Psycopg license](https://github.com/psycopg/psycopg/blob/3.3.9/LICENSE.txt),
and [binary distribution metadata](https://pypi.org/project/psycopg-binary/3.3.9/).
Psycopg documents that its [binary installation](https://www.psycopg.org/psycopg3/docs/basic/install.html#binary-installation)
packages native client libraries. Titanspan does not vendor or modify these
distributions; each is installed separately by the Python package manager.
Applications that redistribute an installed environment must retain the
driver distributions' license files and applicable native-library notices.
