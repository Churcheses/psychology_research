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
    """Gemini APIを呼び出して論文を日本語でわかりやすく解説する"""
    if not GEMINI_API_KEY:
        print("エラー: GEMINI_API_KEYが設定されていません。")
        return None

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
    
    prompt = f"""
以下の心理学論文の情報をもとに、一般の読者が興味を持って読めるWebサイト向けの日本語解説記事を作成してください。

【論文タイトル】
{title}

【アブストラクト】
{abstract}

【出力条件】
必ず以下のJSONフォーマットのみを出力してください（Markdownの ```json 枠などは含めないでください）。

{{
  "title": "親しみやすく読者の興味を惹く日本語タイトル（30文字以内）",
  "summary": "この記事の要点（2〜3文で簡潔に）",
  "background": "なぜこの研究が行われたのか（背景や疑問）",
  "findings": "実験・調査で何がわかったのか（主な発見）",
  "application": "この知識を日常や仕事にどう活かせるか（実践的なアイデア）",
  "category": "関連分野（例：認知心理学、社会心理学、行動心理学、恋愛心理学などから1つ）"
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
