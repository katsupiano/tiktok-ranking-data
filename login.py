"""
Manual login script — run this ONCE on KATSU's Mac.
Opens Chromium, you log into Backstage manually.
When page reaches /portal/workspace/, session is saved to storage_state.json.
"""
from playwright.sync_api import sync_playwright
from pathlib import Path

STORAGE = Path(__file__).parent / "storage_state.json"
LOGIN_URL = "https://live-backstage.tiktok.com/portal/workspace/"


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(locale="ja-JP")
        page = context.new_page()
        page.goto(LOGIN_URL)

        print("\n" + "=" * 60)
        print("ブラウザが開きました")
        print("Backstageにログインしてください（bcodeアカウント）")
        print("ワークスペース画面に到達したら、このターミナルで Enter を押してください")
        print("=" * 60 + "\n")

        input("ログイン完了したらEnterキー: ")

        # Verify we're on a backstage page
        current_url = page.url
        if "backstage.tiktok.com" not in current_url:
            print(f"⚠️  現在のURL: {current_url}")
            print("Backstageにログインできていません。やり直してください。")
            browser.close()
            return

        context.storage_state(path=str(STORAGE))
        print(f"\n✅ セッション保存完了: {STORAGE}")
        print("このファイルは絶対にGitHub publicに出さないでください（Cookieが入ってます）")
        browser.close()


if __name__ == "__main__":
    main()
