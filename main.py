"""
main.py
アプリケーションエントリーポイント。

使い方:
    python main.py
"""

import os
import sys

# プロジェクトルートを sys.path に追加（相対importのため）
sys.path.insert(0, os.path.dirname(__file__))

from ui.app import ThumbnailApp  # noqa: E402


def main():
    app = ThumbnailApp()
    app.mainloop()


if __name__ == "__main__":
    main()
