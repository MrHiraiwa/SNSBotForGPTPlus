tools = [
    {
        "type": "function",
        "function": {
            # 関数の名称
            "name": "scraping",
            # 関数の機能説明
            "description": "URL を指定すると リンクを除くWeb ページの文章が読めます",
            # 関数のパラメータ
            "parameters": {
                "type": "object",
                # 各引数
                "properties": {
                    "link": {
                        "type": "string",
                        # 引数の説明
                        "description": "読みたいページのURL"
                    }
                },
                "required": ["link"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            # 関数の名称
            "name": "scrape_links_and_text",
            # 関数の機能説明
            "description": "URLを指定すると対象ページ内のURLの一覧を取得できます。",
            # 関数のパラメータ
            "parameters": {
                "type": "object",
                # 各引数
                "properties": {
                    "link": {
                        "type": "string",
                        # 引数の説明
                        "description": "読みたいページのURL"
                    }
                },
                "required": ["link"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            # 関数の名称
            "name": "generate_image",
            # 関数の機能説明
            "description": "長い文で描画したいイメージを日本語で具体的に指定すると文章に合った画像が生成できます。描画する人物や物の名前や特徴、ポーズの表情や種類、背景の具体的な要素、全体の色使い、物語のコンテキストや特定のアクセサリー、持ち物など複数の要素を必ず指定してください。",
            # 関数のパラメータ
            "parameters": {
                "type": "object",
                # 各引数
                "properties": {
                    "prompt": {
                        "type": "string",
                        # 引数の説明
                        "description": "描画する人物や物の名前や特徴、ポーズの表情や種類、背景の具体的な要素、全体の色使い、物語のコンテキストや特定のアクセサリー、持ち物など複数の要素を含んだ画像生成の元となる文章。"
                    }
                },
                "required": ["prompt"]
            }
        }
    }
]
