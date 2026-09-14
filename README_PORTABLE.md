# Investment Advisor Tool v4.1 · PORTABLE

이 패키지는 **raw 관세청 DB와 API 키 없이** `data/share_snapshot.sqlite`만 읽는 공유용 버전입니다.

## macOS
```bash
xattr -dr com.apple.quarantine .
chmod +x START_MAC.command
./START_MAC.command
```

## Windows
`START_WINDOWS.bat` 더블클릭.

처음 한 번 Python package 설치가 필요하며 이후에는 바로 실행됩니다. Portable build는 읽기 전용 snapshot이므로 `데이터 최신화` 버튼이 나오지 않습니다.
