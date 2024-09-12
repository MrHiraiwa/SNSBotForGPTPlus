# SNSBotForGPTPlus

このリポジトリは、Cloudrun上で動作するPythonベースのボットです。このボットはChatGPT APIを使用して、WEB上の最新情報をTwitterとInstagram上にツイートします。
このボットは低コストで運用するために3.5turbo向けにチューニングされております。
このボットは料金的にオレゴン（us-west1）に設置することが推奨されます。
このボットプログラムの機能や設置方法についての詳細はありませんが以下のページが参考になります。
https://xxxxx(工事中)

## 機能
以下の機能を持っています。：

- ツイート機能: 指定したページやWEB検索の結果を元につぶやきます。
- スケジュール機能: このスクリプトの機能というよりはGoogle Cloud Platformの機能になりますが決まった時間にツイートします。
- 複数アカウント投稿機能: Twitterの2アカウント、Instagramの1アカウントに対しての同時投稿機能があります。それぞれ有効無効の設定が可能です。お金払ったら大丈夫かもですが無料アカウントで投稿をやりすぎるとバンを食らうので注意してください。

## セットアップ
以下のステップに従ってセットアップしてください：
1. Google Cloud Runでデプロイします：Google Cloud Consoleでプロジェクトを作成しCloud Run APIを有効にし、本レポジトリを指定してデプロイします。 デプロイの際は以下の環境変数を設定する必要があります。
2. 同じプロジェクト内でFirestoreを有効にします：左側のナビゲーションメニューで「Firestore」を選択し、Firestoreをプロジェクトで有効にします。
3. データベースを作成します：Firestoreダッシュボードに移動し、「データベースの作成」をクリックします。データベース名を決めて「ネイティブ」モードを選択します。
4. Custom SearchのAPIを有効にします。
5. TwitterのAPIを有効にし4つのKEY情報を環境変数に登録します。
6. Cloud Strageにファイルが削除されないバケットを設定しオーバレイ画像を設置します。
7. Cloud Strageに1日で画像が消えるスクリプトが作業するワークフォルダを設定します。
8. Cloud SchedulerでCloud runのトリガーURLに「/create」を付与したURLへのアクセスを設定します。
9. Cloud RunのURLに「/login」を付与して管理画面にログインし、パラメータを設定します


## 環境変数
- DATABASE_NAME: Firestoreのデータベース名を入力してください。
- SECRET_KEY: 適当に文字列を入れてください。
- OPENAI_API_KEY: OpenAIのAPIキーを入力してください。
- ADMIN_PASSWORD: WEBの管理画面のログインに使用する管理者パスワードです。このシステムはインターネットから誰でも触れるので、必ず複雑なパスワードを設定してください。
- TWEET1_API_KEY: TwitterのAPIキーを入力してください。
- TWEET1_API_KEY_SECRET: TwitterのAPIキーシークレットを入力してください。
- TWEET1_ACCESS_TOKEN: Twitterのアクセストークンを入力してください。
- TWEET1_ACCESS_TOKEN_SECRET: Twitterのアクセストークンシークレットを入力してください。
- TWEET2_API_KEY: 2アカウント目のTwitterのAPIキーを入力してください。
- TWEET2_API_KEY_SECRET: 2アカウント目のTwitterのAPIキーシークレットを入力してください。
- TWEET2_ACCESS_TOKEN: 2アカウント目のTwitterのアクセストークンを入力してください。
- TWEET2_ACCESS_TOKEN_SECRET: 2アカウント目のTwitterのアクセストークンシークレットを入力してください。
- INSTA_BUSINESS_ACCOUNT: Instagramのビジネスアカウントを入力してください。
- INSTA_ACCESS_TOKEN: Instagramのアクセストークンを入力してください。

## 注意
このアプリケーションはFlaskベースで作成されています。そのため、任意のウェブサーバー上にデプロイすることが可能ですが、前提としてはGoogle Cloud runでの動作を想定しています。デプロイ方法は使用するウェブサーバーによります。

Google Cloud run以外で動作させる場合はFirestoreとの紐づけが必要になります。

## ライセンス
このプロジェクトはMITライセンスの下でライセンスされています。
