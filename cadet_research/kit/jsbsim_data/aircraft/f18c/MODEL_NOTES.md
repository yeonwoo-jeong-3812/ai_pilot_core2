# F/A-18C 교육용 근사 모델

2026-09-27

## 사용 범위

이 XML은 낮은 받음각의 아음속 비행을 살펴보기 위한 독립 JSBSim 모델이다. F/A-18C 실기 공력 데이터나 비행시험으로 검증한 모델이 아니다. 공개된 Hornet 제원 일부를 사용했고, 공력 미계수와 관성은 교육용으로 가정했다. 실기 성능 비교, 고받음각 비행, 실속, 초음속 비행에는 사용하지 않는다.

랜딩기어와 지상 접촉 모델이 없다. 공중에서 초기화해야 하며, 활주·이륙·착륙은 지원하지 않는다. 전술·무장 기능과 실기 FLCS도 포함하지 않는다.

## 공개 제원과 가정

| 항목 | 설정 | 근거와 한계 |
|---|---:|---|
| 공력 기준 날개면적 | 400 ft² | NASA TM-110216의 HARV 기준값. C형 전체 모델 검증을 뜻하지 않는다. |
| 공력 기준 날개폭 | 37.42 ft | 같은 NASA 문헌의 기준값. 외형의 날개 끝 간 거리와 다르다. |
| 기준 시위 | 11.52 ft | NASA TM-110216, 인쇄면 137쪽의 공력 기준 시위. |
| 엔진 | F404-402 근사, 2기 | GE의 F/A-18C/D용 엔진 구분을 사용했다. |
| 엔진별 최대 추력 | 17,700 lbf | GE 공개 정격. XML의 고도별 추력 곡선은 가정이다. |
| 엔진별 비증강 추력 | 11,000 lbf | 교육용 가정. 측정 엔진 덱이 아니다. |
| 공허중량 | 23,050 lb | Museum of Flight의 F/A-18A 전시 기체 제원을 대용했다. C형 실측 중량으로 표시하지 않는다. |
| 조종사 / 초기 연료 | 200 / 5,000 lb | 교육용 적재 가정. |
| 관성·무게중심·연료 위치 | XML 참조 | 모두 가정. |
| 공력 계수 | XML 참조 | 선형 저받음각 계수와 유도항력 근사. 실기 자료에 맞춘 계수가 아니다. |

출처:

- Messina et al., *Simulation Model of the F/A-18 High Angle-of-Attack Research Vehicle Utilized for the Design of Advanced Control Laws*, NASA TM-110216, 1996. [공개 원문](https://ntrs.nasa.gov/api/citations/19960027892/downloads/19960027892.pdf). HARV의 추력편향과 연구용 제어법칙은 구현하지 않았다.
- GE Aerospace, [F404 family data sheet](https://www.geaerospace.com/sites/default/files/2022-01/F404%20Family%20Data%20Sheet_UPDATED.pdf).
- GE, [F404-402 인도 자료](https://www.geaerospace.com/news/press-releases/defense-engines/ge-delivers-first-f404-engine-malaysia-fa-18s).
- Museum of Flight, [McDonnell Douglas F/A-18 Hornet](https://www.museumofflight.org/exhibits-and-events/aircraft/mcdonnell-douglas-fa-18-hornet). 전시 기체는 A형이다.

## 실행과 제어 입력

`core2`에서 다음 명령으로 XML 로드, 공중 초기화, 트림, 짧은 비행 적분을 확인한다.

```powershell
python tools/check_f18c.py
```

엔진은 두 개이므로 수동 스로틀 명령을 넣을 때 `fcs/throttle-cmd-norm[0]`과 `[1]`을 모두 설정한다. 양의 aileron 명령은 오른쪽 롤, elevator 명령은 기수 내림, rudder 명령은 오른쪽 요 방향이다. pitch trim과 elevator 명령을 합산한 뒤 제한한다.

2026-09-27, JSBSim 1.3.1에서 5,000 / 10,000 / 15,000 ft와 250 / 300 / 350 KCAS의 9개 조합이 트림 및 10초 적분 검사를 통과했다. 고도 변화의 절댓값은 최대 약 1.43 ft였다. 양의 세 조종 명령에 대한 각속도 방향과 양 엔진 스로틀 일치도 통과했다. 이 검사는 수치 동작만 확인하며 실기 정확도나 장시간 안정성을 보장하지 않는다.

## 뷰어와의 관계

`tools/acmi_viewer/static/aircraft-lab.html`은 F-16 / F/A-18C 외형 선택과 조종면 리깅 미리보기다. 이 페이지는 JSBSim을 실행하지 않는다. `f18c.js`는 F-16과 같은 `userData.setControls({roll,pitch,yaw})` 인터페이스를 제공한다. F/A-18C의 표시각은 이 XML의 가정한 조종면 범위에 대응한다. 실기 조종면 배분법칙과 동일하지 않다.

`core2`에서 미리보기 서버를 실행한다.

```powershell
python tools/acmi_viewer/server.py --port 18718 --no-open
```

브라우저에서 `http://127.0.0.1:18718/aircraft-lab.html`을 연다. 기존 ACMI 뷰어 상단의 `기체 실습` 링크로도 들어갈 수 있다. 포트를 이미 사용 중이면 다른 포트를 지정한다. 파일을 직접 더블클릭하면 브라우저의 모듈·파일 접근 제한으로 동작하지 않는다.

기존 대전·실시간 비행 경로는 F-16 전용 제어기를 사용하므로 F/A-18C로 바꾸지 않았다. 학생이 실제 비행 시뮬레이션에서 선택하게 하려면 기체별 제어기, 쌍발 입력, 텔레메트리와 외형 ID를 연결하고 따로 검증해야 한다.
