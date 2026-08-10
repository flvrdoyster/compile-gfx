# Compile 그래픽 포맷 디코더 (compile-gfx)

## 개요

Compile 게임의 자체 그래픽 포맷을 PNG로 디코딩하는 파이썬 라이브러리.
디스크스테이션(Windows·DOS)과 PC-98 환세 시리즈에서 쓰인 포맷을 다룸.

**추출 전용.** 재삽입(정확한 크기 맞춤 재압축·아카이브 재구성·디스크 이미지 주입·포인터 테이블)은
각 한글화 프로젝트가 자체적으로 처리하고, 여기에는 그 프로젝트들이 저마다 복사해 두던
코덱·컨테이너 지식만 모음. 압축기도 해제기 옆에 같이 둠 — 같은 옵코드 테이블의 양면이라
떨어뜨리면 갈라지기 때문 (배경은 [`FORMATS.md`](FORMATS.md) 참고).

| 확장자 | 압축 | 페이로드 헤더 | 사용처 |
|---|---|---|---|
| `.GCN` `.CNS` `.CNU` | GCN 토큰 스트림 | 8바이트 (구형) | 디스크스테이션 vol.12·14·20 |
| `.GCS` | GCN 토큰 스트림 | `GMP-200` | vol.20 `DSMENU` |
| `.GMP` | 없음 (생 데이터) | `GMP-200` | vol.14 `MADOADV` |
| `.CNX` | 2비트 태그 | `GMP-200` | vol.20 `haiyuki` |
| `.CNS` (vol.10) | Compile PC-98 LZ | PC-98 플레이너 | 디스크스테이션 vol.10 |
| `.CND` | PC-98 RLE | PC-98 플레이너 | 미검증 (해당 파일 없음) |

확장자로 판단하지 않고 내용으로 판별함. 같은 `.CNS`가 vol.12·14·20에서는 Windows LZ 이미지,
vol.10에서는 DOS 플레이너 이미지로 전혀 다름.

### 구성

+ **`src/compilegfx/codec/`** — 압축 코덱. `gcn`(Windows LZ) · `cnx`(2비트 태그) ·
`pc98lz`(DOS/PC-98 LZ, 압축기 포함) · `pc98rle`.
+ **`src/compilegfx/container/`** — 페이로드 해석. `header8`(구형 8바이트 헤더) ·
`gmp200` · `planar`(PC-98 비트플레인) · `palette`(외부 팔레트 테이블).
+ **`src/compilegfx/`** — `detect.py`(내용 기반 판별) · `image.py`(`Bitmap` 타입·PNG 출력) ·
`cli.py`.
+ **`tests/`** — 코덱 단위 테스트와 실제 디스크 대조 회귀. 게임 데이터는 저장소에 없고
`vectors/corpus.json`에 디코딩 결과 해시만 둠.

---

## 사용법

### 설치

```bash
pip install git+https://github.com/flvrdoyster/compile-gfx
```

PNG 출력에만 Pillow가 필요하고 디코더 자체는 표준 라이브러리만 씀.
PNG까지 쓰려면 `pip install "compile-gfx[png] @ git+https://github.com/flvrdoyster/compile-gfx"`.

### 명령줄

```bash
compile-gfx one   MAIN14.GCN out.png
compile-gfx batch ds14/data  ds14/png     # 트리 전체, 폴더 구조 그대로
compile-gfx pc98  ds10/data/MAIN_DAT ds10/png
```

`batch`는 파일 내용으로 포맷을 판별하므로 Windows 계열 전 확장자를 한 번에 처리.
결과를 셋으로 구분해 보고함 — 변환 성공, **스킵**(그래픽 확장자지만 이미지가 아닌 파일 —
사례는 [`FORMATS.md`](FORMATS.md)), **실패**(진짜 예상 밖).

vol.10은 매직이 없고 팔레트를 `MAIN_DAT/MENU.DAT`에서 따로 가져오므로 `pc98`을 씀.

### 라이브러리

```python
import compilegfx

bmp = compilegfx.load(open("MAIN14.GCN", "rb").read())
compilegfx.to_png(bmp, "out.png")
```

vol.10 파일은 팔레트를 함께 넘겨 조립.

```python
from compilegfx.codec import pc98lz
from compilegfx.container import palette, planar

pal = palette.read_menu_dat(open("MENU.DAT", "rb").read())["DS10_T.CNS"]
buf = pc98lz.decompress(open("DS10_T.CNS", "rb").read())
compilegfx.to_png(planar.to_bitmap(buf, pal), "out.png")
```

### 테스트

```bash
pytest tests/test_codecs.py                    # 게임 데이터 불필요
COMPILE_GFX_CORPUS=<추출본 경로> pytest         # + 2,064개 파일 회귀
```

`tests/vectors/corpus.json`은 해시만 담고 있어 로컬에 있는 파일만 대조함.
갱신은 `python tests/make_manifest.py <경로>` — 출력이 **바뀌어야 할 때만**.

---

## 기술 노트

옵코드 표, 헤더 레이아웃, 행 순서·팔레트 관련 함정, 역공학 출처 등 포맷 상세는
[`FORMATS.md`](FORMATS.md) 참고.

---

## 크레딧

**CNS·CNX 컨버터**: cns110.exe · cnx106.exe by mkjpg (2005) — CNX 2비트 태그 코덱은 이
실행 파일을 디스어셈블해 확정  
**PC-98 LZ·플레이너**: [gensei-pc98](https://github.com/flvrdoyster/gensei-pc98) by flvrdoyster  
**CNS 팔레트 필드·4bpp 분기**: [suiko-web-v2](https://github.com/flvrdoyster/suiko-web-v2) by flvrdoyster  
**라이브러리 구성**: flvrdoyster

---

## 소프트웨어 고지 / Software Notice

본 저장소는 Compile 게임의 그래픽 포맷을 해석하는 도구만 포함합니다. 게임 데이터는 저장소에
포함하지 않으며, 사용하려면 원본 디스크를 직접 준비해야 합니다.

원본 게임은 Compile이 개발하였으며, 게임 자산(그래픽, 음악 등)의 모든 권리는 원저작권자에게
있습니다.

본 프로젝트는 비상업적 보존 및 한글화 목적으로만 운영됩니다.
저작권자로서 자료 삭제를 원하실 경우 Issue를 열어주시면 즉시 대응하겠습니다.

This repository contains only tools for interpreting the graphics formats used in Compile's
games. No game data is included; you need your own copies of the original discs to use it.

The games were originally developed by Compile. All rights to the games and their assets
(graphics, music, etc.) belong to their respective copyright holders.

This project exists solely for non-commercial preservation and Korean localization.
If you are a rights holder and would like this material removed, please open an issue and it
will be promptly addressed.
