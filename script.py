import os
import json
import urllib.request
import urllib.parse
from datetime import datetime

# 設定情報
DATA_FILE = "data/papers.json"
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

def load_existing_papers():
    """既存の論文データを読み込む"""
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"既存データの読み込みエラー: {e}")
            return []
    return []

def reconstruct_abstract(inverted_index):
    """OpenAlexのInverted Index形式からテキストのアブストラクトを復元する"""
    if not inverted_index:
        return ""
    word_positions = []
    for word, positions in inverted_index.items():
        for pos in positions:
            word_positions.append((pos, word))
    word_positions.sort(key=lambda x: x[0])
    return " ".join([word for _, word in word_positions])

def fetch_psychology_paper(existing_ids):
    """OpenAlex APIから最新の心理学論文を1件取得する"""
    # OpenAlex Works API (心理学コンセプト: C15744967, アブストラクトあり, 英語)
    url = "https://api.openalex.org/works?filter=has_abstract:true,concepts.id:C15744967,language:en&sort=publication_date:desc&per-page=20"
    
    req = urllib.request.Request(url, headers={'User-Agent': 'PsychologyAutoBlog/1.0 (mailto:example@example.com)'})
    
    try:
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode('utf-8'))
            results = data.get("results", [])
            
            # まだ取り込んでいない最新の論文を1件選ぶ
            for item in results:
                paper_id = item.get("id")
                if paper_id not in existing_ids:
                    abstract_index = item.get("abstract_inverted_index")
                    abstract = reconstruct_abstract(abstract_index)
                    
                    # アブストラクトが短すぎるものはスキップ
                    if len(abstract) < 100:
                        continue
                        
                    return {
                        "id": paper_id,
                        "doi": item.get("doi", ""),
                        "original_title": item.get("title", ""),
                        "publication_date": item.get("publication_date", ""),
                        "abstract": abstract,
                        "url": item.get("doi") or item.get("id")
                    }
    except Exception as e:
        print(f"OpenAlex APIエラー: {e}")
    return None

def summarize_with_gemini(title, abstract):
    """Gemini APIを呼び出して、初心者向け解説・具体的活用・複数論文に通底する知見を作成する"""
    if not GEMINI_API_KEY:
        print("エラー: GEMINI_API_KEYが設定されていません。")
        return None

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
    
    prompt = f"""
以下の心理学論文の情報をもとに、専門知識がない初心者や中学生でも一目で理解できるようにわかりやすく解説記事を作成してください。

【論文タイトル】
{title}

【アブストラクト】
{abstract}

【出力条件】
専門用語は避け、身近な例え話や比喩を使ってください。
必ず以下のJSONフォーマットのみを出力してください（Markdownの ```json 枠などは含めないでください）。

{{
  "title": "初心者でも惹かれる日本語タイトル（30文字以内）",
  "summary": "超要約（心理学専攻者に1文のまとめ/ユーモアを持たせる）",
  "background": "なぜこの研究をしたのか（日常生活の身近な疑問に例えて説明）",
  "findings": "何がわかったのか（難しい数値を使わず直感的に説明）",
  "overall_insight": "【複数論文の横断知見】この研究だけでなく、関連する心理学全般から言える総合的な知見や共通テーマ",
  "application_scene": "日常で活かせる具体的な場面（例：朝の勉強中、仕事でミスした直後、人間関係で悩んだ時，上手くいかなくて落ち込んだ時など）",
  "application_action": "具体的な行動手順（例：「まず〜し、次に〜する」といった実践ステップ）",
  "category": "カテゴリ（認知心理学、行動心理学、社会心理学、メンタルヘルスなどから1つ）"
}}
"""

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "response_mime_type": "application/json"
        }
    }
    
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json'}
    )
    
    try:
        with urllib.request.urlopen(req) as response:
            res_data = json.loads(response.read().decode('utf-8'))
            text = res_data['candidates'][0]['content']['parts'][0]['text']
            return json.loads(text)
    except Exception as e:
        print(f"Gemini API呼び出しエラー: {e}")
        return None

def main():
    print("=== 心理学論文の自動収集・要約処理を開始します ===")
    
    # 1. 既存データの読み込み
    papers = load_existing_papers()
    existing_ids = {p.get("id") for p in papers if "id" in p}
    print(f"現在保持している論文数: {len(papers)}件")
    
    # 2. 未取得の論文を1件選定
    raw_paper = fetch_psychology_paper(existing_ids)
    if not raw_paper:
        print("新しい論文が見つかりませんでした。処理を終了します。")
        return
        
    print(f"対象論文を取得: {raw_paper['original_title']}")
    
    # 3. Gemini APIで要約を作成
    ai_result = summarize_with_gemini(raw_paper["original_title"], raw_paper["abstract"])
    if not ai_result:
        print("要約の作成に失敗しました。")
        return
        
    # 4. データの整形と蓄積
    new_data = {
        "id": raw_paper["id"],
        "added_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "original_title": raw_paper["original_title"],
        "publication_date": raw_paper["publication_date"],
        "url": raw_paper["url"],
        "title": ai_result.get("title"),
        "summary": ai_result.get("summary"),
        "background": ai_result.get("background"),
        "findings": ai_result.get("findings"),
        "application": ai_result.get("application"),
        "category": ai_result.get("category", "心理学一般")
    }
    
    # 配列の先頭に追加（新しいものが上に来るようにする）
    papers.insert(0, new_data)
    
    # 5. 保存
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(papers, f, ensure_ascii=False, indent=2)
        
    print(f"成功: 『{new_data['title']}』を {DATA_FILE} に追加保存しました！")

if __name__ == "__main__":
    main()
