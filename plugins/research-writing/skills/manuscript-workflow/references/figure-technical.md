# 도판 — 기술 규칙

캡션 문단의 스타일 · Word 필드 · 산출물 검증은 빌드 쪽 규칙이라 `build-technical.md` 에 있습니다.

## 투명 배경은 반드시 흰색 위에 합성합니다

원고 도판은 대부분 **RGBA(투명 배경) TIFF/PNG**입니다. 이것을 `.convert('RGB')`로 바로 바꾸면
투명 영역이 **검은색**으로 채워집니다. 실제로 이 때문에 도판 하나가 완전 검정 한 색이 되고
여러 도판의 배경이 검게 나온 적이 있습니다.

```python
im = Image.open(src)
if im.mode in ('RGBA','LA') or (im.mode=='P' and 'transparency' in im.info):
    im = im.convert('RGBA')
    bg = Image.new('RGB', im.size, (255,255,255))
    bg.paste(im, mask=im.split()[-1])          # 흰색 위에 합성
    im = bg
else:
    im = im.convert('RGB')
```

도판을 새로 넣거나 바꾼 뒤에는 **모서리 픽셀 평균과 고유색 수로 자가 진단**합니다.
모서리 평균이 60 미만이면 검은 배경, 고유색이 2개 이하면 깨진 파일입니다.

## 도판에 남기지 않는 것

- 소프트웨어 UI 스크린샷 (EDS 정량 대화상자, 측정 프로그램 창)
- 자동 생성 제목 텍스트 (`EBSD Layered Image 10` 등)
- 슬라이드 장식 요소 (색 머리띠, 로고, 페이지 번호)

**이 목록이 겨냥하는 것은 도판을 읽는 데 방해가 되는 것입니다.** 분석·계산 프로그램이 출력에 자동으로
찍는 표기는 방해가 되지 않으면 그대로 둡니다.

수치를 보여야 하면 같은 값으로 **정식 표를 다시 그립니다**. 표로 바꾸면 본문·캡션의 표현도
함께 고쳐야 합니다 (`spectrum` → `quantification result`).
