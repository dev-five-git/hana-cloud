# Hana Registry

Hana Registry는 한번(HanBeon)이 사용하는 응용 프로그램 프로필과 외부 보드
자료를 배포하는 공개 데이터 저장소입니다. 실행 코드와 업로더 구현은 두지 않고,
검토 가능한 JSON·펌웨어·이미지만 관리합니다.

## 저장소 구조

```text
.gitattributes
registry.json
apps/
  music-app.json
  pdf-viewer.json
boards/
  arduino-uno-r3.json
  arduino-uno-r3.ino
  arduino-uno-r3.png
contracts/
  normalization-examples.json
schemas/
  app.schema.json
  board.schema.json
  normalization-examples.schema.json
  registry.schema.json
```

`registry.json`은 항상 저장소 루트에 존재합니다. 클라이언트는 이 파일만 주기적으로
확인하고, 일치하는 응용 프로그램 프로필이나 보드 manifest를 필요할 때 내려받습니다.
아래 JSON 블록은 필드 구조를 설명하는 축약 예시입니다. 실제 항목과 해시는
`registry.json`과 각 manifest를 기준으로 합니다.

## 루트 인덱스

```json
{
  "schemaVersion": 1,
  "revision": 2,
  "apps": [
    {
      "id": "pdf-viewer",
      "name": "PDF 뷰어",
      "path": "apps/pdf-viewer.json",
      "sha256": "64자리 소문자 SHA-256",
      "match": {
        "macos": { "bundleIds": ["com.apple.Preview"] }
      }
    }
  ],
  "boards": [
    {
      "id": "arduino.uno-r3",
      "name": "Arduino Uno R3",
      "manifest": "boards/arduino-uno-r3.json",
      "sha256": "64자리 소문자 SHA-256",
      "detect": {
        "usb": [
          {
            "vid": "2341",
            "pid": "0043",
            "confidence": "exact",
            "manufacturerAliases": ["Arduino", "Arduino LLC", "Arduino (www.arduino.cc)"],
            "productAliases": ["Arduino Uno", "Arduino Uno R3"]
          }
        ]
      }
    }
  ]
}
```

- `schemaVersion`은 호환되지 않는 구조 변경에서만 증가합니다.
- `revision`은 인덱스 내용이 바뀔 때마다 1씩 증가합니다.
- `id`는 종류 안에서 유일한 소문자 점 표기 식별자입니다.
- 모든 경로는 저장소 루트 기준 상대 경로이며 `..`, URL, 역슬래시를 허용하지 않습니다.
- `sha256`은 대상 파일의 바이트를 계산한 64자리 소문자 16진수입니다.
- 앱의 플랫폼 식별자는 표시 이름 정규화를 적용하지 않습니다. Windows 실행 파일명은
  basename과 Unicode 소문자로 비교하고, macOS bundle ID와 Linux desktop ID·WM_CLASS는
  registry에 등록된 명시적 별칭과 비교합니다. 플랫폼 항목을 등록했다면 별칭 배열은
  비어 있을 수 없고, Windows 값에는 경로가 아닌 `.exe` basename만 허용합니다.
- 보드는 공장 출하 상태에서도 얻을 수 있는 USB VID/PID로 후보를 찾습니다. 선택적인
  `manufacturerAliases`와 `productAliases`는 후보를 좁히는 힌트이며 단독 식별자로
  쓰지 않습니다.
- `confidence`가 `exact`이고 후보가 하나일 때만 자동 확정합니다. `likely`는 추천만,
  `ambiguous` 또는 여러 후보는 사용자 선택으로 넘깁니다.
- USB descriptor 필드가 운영체제에서 제공되지 않으면 중립으로 처리합니다. 제공된
  manufacturer 또는 product가 해당 aliases와 일치하면 현재 confidence를 유지하고,
  하나라도 불일치하면 후보를 버리지 않고 `ambiguous`로 낮춥니다. descriptor 일치는
  VID/PID가 정한 confidence를 더 높은 단계로 올리지 않습니다.

## 응용 프로그램 프로필

```json
{
  "schemaVersion": 1,
  "id": "pdf-viewer",
  "actions": [
    {
      "label": "다음 장",
      "name": "페이지 넘기기",
      "shortcut": {
        "macos": "pagedown",
        "windows": "pagedown",
        "linux": "pagedown"
      }
    }
  ]
}
```

- 프로필의 `id`는 `registry.json` 항목과 정확히 같아야 합니다.
- `actions`는 최대 3개입니다. 앞의 기본 4칸과 설정 칸의 순서는 바꾸지 않습니다.
- `label`은 20자, `name`은 60자를 넘지 않습니다.
- 각 단축키는 한번 클라이언트의 제한된 단축키 문법으로 해석할 수 있어야 합니다.
- 단축키는 공백 없는 소문자 표준형으로 저장합니다.
- 명령 실행 파일, 셸 문자열, 스크립트 URL은 허용하지 않습니다.
- 지원하지 않는 플랫폼의 단축키는 생략할 수 있으며, 그 플랫폼에서는 해당 칸을
  만들지 않습니다.

## 보드 manifest

```json
{
  "schemaVersion": 1,
  "id": "arduino.uno-r3",
  "firmware": {
    "path": "boards/arduino-uno-r3.ino",
    "format": "arduino-sketch",
    "fqbn": "arduino:avr:uno",
    "sha256": "64자리 소문자 SHA-256"
  },
  "wiring": [
    {
      "from": "D2",
      "to": "순간 누름 스위치 NO 단자",
      "note": "스위치 COM 단자는 GND에 연결"
    },
    {
      "from": "D9",
      "to": "LED 양극",
      "note": "220~330Ω 직렬 저항을 사용하고 LED 음극은 GND에 연결"
    }
  ],
  "image": {
    "path": "boards/arduino-uno-r3.png",
    "sha256": "64자리 소문자 SHA-256",
    "alt": "Arduino Uno R3의 D2 스위치와 D9 LED 연결 배선도"
  }
}
```

- `id`는 `registry.json` 보드 항목과 정확히 같아야 합니다.
- `firmware.path`와 선택적인 `image.path`는 같은 보드 basename을 사용합니다.
- 이미지를 제공하면 스크린 리더용 `alt` 설명이 반드시 있어야 합니다.
- 클라이언트는 manifest, 펌웨어, 이미지의 해시를 모두 확인한 뒤에만 로컬 경로를
  업로더 인터페이스에 넘깁니다.
- 펌웨어 다운로드와 업로더 호출은 사용자가 설치를 명시적으로 시작한 뒤에만
  수행합니다. 보드를 감지했다는 이유만으로 자동 실행하지 않습니다.
- 탐색 단계에서는 시리얼 포트를 열거나 handshake를 보내지 않습니다. 새 보드에는
  Hana 펌웨어가 없고, Uno 계열은 포트를 여는 것만으로도 리셋될 수 있습니다.
- USB 정보가 여러 보드와 일치하거나 등록되지 않은 클론 보드이면 자동 확정하지 않고,
  사용자가 지원 보드 목록에서 모델을 고르게 합니다.

## 식별자와 문자열 정규화

정규화는 USB의 제조사·제품 표시 문자열처럼 사람이 읽는 보조 정보에만 적용합니다.

1. Unicode NFKC로 호환 문자를 정규화합니다.
2. 앞뒤 공백을 제거하고 Unicode 소문자로 변환합니다.
3. 하나 이상의 Unicode 공백, ASCII `_`, ASCII `-`를 단일 `-`로 바꿉니다.
4. 결과 양끝의 `-`를 제거합니다.

그 밖의 Unicode 문자와 괄호·점 등의 문자는 제거하지 않고 보존합니다.

따라서 ` Arduino UNO_R3 `, `arduino-uno r3`, `Ａｒｄｕｉｎｏ　ＵＮＯ－Ｒ３`는 모두
`arduino-uno-r3`가 됩니다. 공통 테스트 벡터는 `contracts/normalization-examples.json`에
있으며 모든 클라이언트 구현은 같은 결과를 내야 합니다.

registry `id`, 상대 경로, SHA-256, macOS bundle ID, Linux desktop ID·WM_CLASS에는 이
표시 문자열 정규화를 적용하지 않습니다. 이 값은 문법을 검증하고 등록된 별칭과
비교합니다. VID/PID는 숫자 `u16`으로 파싱한 뒤 정확히 네 자리 소문자 hex로 직렬화하여
`0x2A03`과 `2a03` 같은 표기 차이를 제거합니다.

## 보드 식별 한계

공식 Arduino 플랫폼이 Uno에 배정한 VID/PID는 `arduino:avr:uno` 대상으로 확정할 수
있습니다. 반면 CH340·FT232 같은 범용 USB-시리얼 칩의 VID/PID는 칩만 식별하고, 그 칩이
장착된 보드 모델은 식별하지 못합니다. USB product·manufacturer·serial number와 포트
경로는 보조 힌트일 뿐입니다. MCU signature도 ATmega328P 같은 칩 종류만 알려주므로
정확한 보드 모델 판별이나 최초 자동 업로드의 근거로 사용하지 않습니다.

Uno의 VID/PID 목록과 USB 문자열은 Arduino의
[`boards.txt`](https://github.com/arduino/ArduinoCore-avr/blob/master/boards.txt)와
[`Descriptors.c`](https://github.com/arduino/ArduinoCore-avr/blob/master/firmwares/atmegaxxu2/arduino-usbserial/Descriptors.c)를
기준으로 관리합니다. 범용 USB-시리얼 칩의 자동 식별 한계는
[Arduino CLI FAQ](https://docs.arduino.cc/arduino-cli/FAQ)와 같습니다.

## 클라이언트 계약

실행 로직은 `dev-five-git/hanbeon`에 둡니다.

1. 백그라운드 갱신기가 시작 시와 마지막 성공 후 24시간이 지났을 때
   `registry.json`을 조건부 요청합니다.
2. 포커스 감지 루프는 네트워크를 호출하지 않고 메모리 인덱스와 캐시만 조회합니다.
3. 일치하는 프로필이 캐시에 없을 때 한 번만 내려받아 스키마·크기·SHA-256을
   검증하고 last-known-good 캐시에 원자적으로 저장합니다.
4. 새 프로필 적용 시 `미리보기 프로필 인식 완료 · 버튼 2개 추가`처럼 한 번만
   알립니다. 다운로드 중이거나 실패한 상태를 300ms 폴링마다 반복 표시하지 않습니다.
5. 네트워크·검증 실패 시 마지막 정상 캐시를 유지하고, 캐시도 없으면 한번에 내장된
   기본 프리셋 또는 기본 4칸으로 동작합니다.

현재 HanBeon 펌웨어의 `HANBEON_UNO_V1` handshake는 펌웨어 설치가 끝난 보드와
런타임 연결을 맺는 기존 프로토콜로만 유지합니다. 최초 보드 식별이나 레지스트리
매칭 조건에는 사용하지 않습니다.

다운로드는 HTTPS `raw.githubusercontent.com/dev-five-git/hana-registry`로 고정하고,
리다이렉트 후 host 변경을 허용하지 않습니다. 제한은 인덱스 256KiB, 앱 프로필
64KiB, 보드 manifest 64KiB, 펌웨어 2MiB, 이미지 5MiB, 요청당 5초입니다.

## 플랫폼 식별자

- macOS: `NSWorkspace.frontmostApplication`의 bundle ID
- Windows: foreground HWND의 PID로 얻은 실행 파일명
- Linux X11: `_NET_ACTIVE_WINDOW`의 `WM_CLASS`와 desktop ID
- Linux Wayland: 데스크톱 환경이 안전한 활성 앱 식별자를 제공하는 어댑터만 사용;
  사용할 수 없으면 앱 프로필을 적용하지 않고 기본 4칸을 유지

OS별 코드는 같은 `FocusedApplication` 인터페이스로 정규화하고, 레지스트리 조회와
UI는 플랫폼 조건문을 갖지 않습니다.

## 구현 Wave

각 Wave는 독립적인 PR로 검토하고 앞 Wave가 병합된 뒤 다음 Wave를 시작합니다.

1. **Registry foundation** — 이 저장소의 `registry.json`, 샘플 앱/보드 자료,
   README 계약을 추가합니다.
2. **Focus adapters** — HanBeon에 macOS·Windows·Linux 활성 앱 식별 어댑터와
   단위 테스트를 추가합니다. 네트워크는 포함하지 않습니다.
3. **App profiles** — 인덱스 갱신, 프로필 검증·캐시·적용, 인식 완료 메시지를
   추가합니다.
4. **Board catalog** — 보드 자료 검증·캐시, 배선 안내 UI, 다른 작업자가 구현하는
   업로더에 넘길 안정적인 인터페이스를 추가합니다. 업로드 구현은 포함하지 않습니다.
5. **Desktop releases** — Changepacks가 만든 draft release에 Windows, macOS,
   Linux Tauri 번들을 올리고 모든 빌드 성공 후 release를 공개합니다.

## 변경 규칙

- 데이터 변경은 PR로만 받습니다.
- `registry.json`과 대상 파일은 같은 PR에서 함께 갱신합니다.
- 기존 `id`의 의미를 바꾸지 않습니다. 호환되지 않는 변경은 새 `id` 또는 새
  `schemaVersion`을 사용합니다.
- 저작권이나 재배포 권한을 확인할 수 없는 펌웨어와 이미지는 추가하지 않습니다.
