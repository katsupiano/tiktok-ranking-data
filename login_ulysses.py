"""Ulysses agency login — saves storage_state_ulysses.json.
Run this ONCE with the katsuaki.takizawa.grove@gmail.com account."""
from playwright.sync_api import sync_playwright
from pathlib import Path

STORAGE = Path(__file__).parent / "storage_state_ulysses.json"
LOGIN_URL = "https://live-backstage.tiktok.com/portal/workspace/"


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(locale="ja-JP")
        page = context.new_page()
        page.goto(LOGIN_URL)

        print("\n" + "=" * 60)
        print("ユリシスアカウントでBackstageログインしてください")
        print("(katsuaki.takizawa.grove@gmail.com)")
        print("ワークスペース画面に到達したら Enter")
        print("=" * 60 + "\n")

        input("ログイン完了したらEnterキー: ")

        if "backstage.tiktok.com" not in page.url:
            print(f"⚠️  現在のURL: {page.url}")
            browser.close()
            return

        context.storage_state(path=str(STORAGE))
        print(f"\n✅ ユリシスセッション保存完了: {STORAGE}")
        browser.close()


if __name__ == "__main__":
    main()
