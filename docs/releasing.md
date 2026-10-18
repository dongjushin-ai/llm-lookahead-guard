# 릴리스 방법 (PyPI)

`v*` 태그를 push하면 `.github/workflows/release.yml`이 테스트 → 빌드(`python -m build`, `twine check`) → PyPI 업로드를 순서대로 실행합니다. 업로드는 PyPI **Trusted Publishing**(OIDC)이라 API 토큰을 저장소에 넣지 않습니다.

## 처음 한 번만 (DockY)

1. **PyPI 계정**: <https://pypi.org/account/register/> 가입 → 이메일 인증 → 2단계 인증(2FA) 켜기.
2. **Trusted Publisher 등록**: PyPI → Your account → Publishing → *Add a new pending publisher* → GitHub 탭에 아래 값을 그대로 입력.

   | 항목 | 값 |
   |---|---|
   | PyPI Project Name | `llm-lookahead-guard` |
   | Owner | `dongjushin-ai` |
   | Repository name | `llm-lookahead-guard` |
   | Workflow name | `release.yml` |
   | Environment name | `pypi` |

   "pending" 상태로 등록해 두면 첫 업로드 때 프로젝트가 만들어집니다(2026-10-18 기준 이 이름은 비어 있음).
3. **GitHub environment**: 저장소 Settings → Environments → `pypi` 만들기. 원하면 *Required reviewers*에 본인을 넣어 업로드 직전에 한 번 더 승인하게 할 수 있습니다. (만들지 않아도 첫 실행 때 자동 생성됩니다.)

## 매 릴리스

1. `pyproject.toml`의 `version`을 올리고 main에 커밋·push → CI 초록불 확인.
2. 태그 push (태그는 반드시 `v` + pyproject 버전과 같아야 함, 다르면 build 단계에서 멈춤):

   ```bash
   git tag v0.1.0
   git push origin v0.1.0
   ```

3. GitHub Actions → *Release* 실행 확인 → <https://pypi.org/project/llm-lookahead-guard/> 에서 새 버전 확인.
4. 첫 배포 뒤에는 README 두 개의 설치 줄을 `pip install llm-lookahead-guard`로 바꿉니다.

## 참고

- 같은 버전 번호는 PyPI에 두 번 올릴 수 없습니다. 실패하면 버전을 올려 새 태그를 만드세요.
- 로컬 점검만 하려면: `pip install build twine && python -m build && twine check --strict dist/*` (`dist/`는 커밋하지 않음, `.gitignore`에 있음).
- 데모 GIF 다시 만들기: `python docs/assets/make_demo_gif.py` (Playwright + Chromium, ffmpeg 필요).
