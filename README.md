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
| `.CNX` | 2비트 태그 | `GMP-200` | vol.20 (패유기·comet·PuyoEd20) |
| `.CNS` (vol.10) | Compile PC-98 LZ | PC-98 플레이너 | 디스크스테이션 vol.10 |
| `.CND` | PC-98 RLE | PC-98 플레이너 | 미검증 (해당 파일 없음) |
| `.DAT` (`gcs v1.4`) | 세로 RLE | PC-98 플레이너 | 환세풍광전 타이틀·오프닝·엔딩 |

확장자로 판단하지 않고 내용으로 판별함. 같은 `.CNS`가 vol.12·14·20에서는 Windows LZ 이미지,
vol.10에서는 DOS 플레이너 이미지로 전혀 다름.

### 구성

+ **`src/compilegfx/codec/`** — 압축 코덱. `gcn`(Windows LZ) · `cnx`(2비트 태그) ·
`pc98lz`(DOS/PC-98 LZ, 압축기 포함) · `pc98rle`.
+ **`src/compilegfx/container/`** — 페이로드 해석. `header8`(구형 8바이트 헤더) ·
`gmp200` · `planar`(PC-98 비트플레인) · `palette`(외부/스크립트 팔레트 테이블) ·
`chunked`(환세 시리즈 청크 테이블) · `tilesheet`(256타일 5플레인 스프라이트시트) ·
`gcs14`(풍광전 화면) · `cells`(16x16 4플레인 조각, 시트 PNG와 왕복) ·
`fld`(취호전 아카이브) · `tilemap`(이미지가 아닌 격자 데이터 판별).
+ **`src/compilegfx/script/`** — `sp1`(희담 데모 `SP1.COM`의 연출 스크립트 재생기, 프레임별 조각 출처 기록).
+ **`src/compilegfx/`** — `extract.py`(폴더 전체 판별·추출) · `detect.py`(Windows 계열 판별) ·
`image.py`(`Bitmap` 타입·PNG 출력) · `cli.py`.
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
compile-gfx extract <게임 폴더 또는 파일> <출력 폴더>
```

아는 형식이면 어떤 파일이 어떤 형식인지 몰라도 됨. 폴더 안 파일을 하나하나 내용으로 판별하고, FLD 아카이브나
청크형 `DAT` 같은 묶음 파일은 안까지 열어서 그림을 모두 뽑음. 출력 폴더는 입력 폴더 구조를
따르고, 묶음 파일 안의 그림은 그 파일 이름의 폴더 아래에 들어감(`GENSE.FLD/xxx.png`,
`DISK_C.DAT/c02.png`).

**범용 추출기는 아님.** 지금까지 실제 데이터로 확인한 범위는 디스크스테이션 vol.8·10·12·14·20,
취호전, 패유기·쾌신 Windows판, PC-98 환세 시리즈(쾌도전·포물장·풍광전·희담)뿐이고, 그 밖의
Compile 게임은 형식이 맞으면 되지만 보장하지 않음. 알려진 구멍:

- PC-98 계열은 장면마다 다른 팔레트를 파일 밖에서 지정하는데, 자동으로 확정되는 건 일부뿐임
  (`스크립트 근거`·`파일 내장`·`팔레트 표` 외는 추정).
- 디스크 이미지(FDI·HDI·D88·ISO)는 안을 열지 못함 — 파일을 먼저 꺼내야 함.
- 희담처럼 그래픽이 낱개 파일이고 연출 스크립트가 따로 있는 경우는 해석기가 확인된 판본(희담 데모
  `SP1.COM`)만 재생함.
- MSX와 게임기(메가드라이브·슈퍼패미컴·새턴 등) 형식은 없음.

끝나면 `<출력 폴더>/extract_report.tsv`에 파일마다 결과가 남음:

| 열 | 내용 |
|---|---|
| 상태 | `변환` / `건너뜀`(그림이 아님 — 텍스트·스크립트·맵·동영상 등) / `판별 불가`(아는 형식에 안 맞음) |
| 형식 | 판별한 형식과 크기 |
| 팔레트 | `파일 내장`·`팔레트 표`(확정), `스크립트 근거`(스크립트가 그 그림 주변에서 지정하는 팔레트가 하나뿐), `스크립트 최빈값(추정)`·`기본값(추정)` |
| 비고 | 판별 근거나 단서 |

팔레트가 **추정**인 그림은 색이 틀릴 수 있음. 환세 본편(`DISK_B`/`DISK_C`)은 스크립트가 그림 주변에서
지정하는 팔레트가 둘 이상이면 `<이름>_palettes.png`에 후보별 그림이 함께 나오니 눈으로 고르면 됨. PC-98 계열은 팔레트가 그림 파일 밖(스크립트 등)에
있어서, 장면마다 다른 팔레트를 쓰는 그림은 아직 자동으로 못 맞춤. 그런 그림은 아래 세부 도구로
팔레트를 직접 지정함. `판별 불가` 목록은 아직 모르는 형식의 단서임.

#### 세부 도구

```bash
compile-gfx chunks   kaitou/DISK_C.DAT kaitou/png  # 청크형 DAT 하나
compile-gfx palettes kaitou/DISK_B.DAT --chunk 1   # 스크립트 팔레트 후보 나열
compile-gfx files    hukyou hukyou/png             # 낱개 파일 폴더 (--palette, --mask)
compile-gfx one      MAIN14.GCN out.png            # Windows 계열 파일 하나
```

`chunks`·`files`의 `--palette`는 16진 니블 표기를 받음:

```bash
compile-gfx files hukyou out/ --only TITLE.DAT \
  --palette "000 f98 333 f03 766 730 fed fb9 b75 f00 900 c99 ebb fcc fdd fff"
```

어느 팔레트인지 모를 때는 후보 전부로 그린 컨택트 시트를 보고 고름:

```bash
compile-gfx chunks DISK_C.DAT out/ --chunk 45 --try-palettes DISK_B.DAT
```

후보 순서(첫 등장 순)는 고정이라 "45번 청크는 3번 팔레트" 같은 메모가 그대로 유효함.
게임별로 확인된 장면 팔레트는 [`FORMATS.md`](FORMATS.md) 참고.

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
COMPILE_GFX_CORPUS=<추출본 경로> pytest         # + 2,051개 파일 회귀
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
