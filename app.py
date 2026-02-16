"""
🎬 YouTube 콘텐츠 제작 도우미 v2.0
트렌드 분석 + 대본 생성 (웹 배포 버전)

Streamlit Cloud 배포용
"""
import streamlit as st
import json
import os
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import re

# API 클라이언트
try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

try:
    from googleapiclient.discovery import build
    YOUTUBE_API_AVAILABLE = True
except ImportError:
    YOUTUBE_API_AVAILABLE = False

try:
    from pytrends.request import TrendReq
    PYTRENDS_AVAILABLE = True
except ImportError:
    PYTRENDS_AVAILABLE = False


# ============ 페이지 설정 ============

st.set_page_config(
    page_title="YouTube 콘텐츠 제작 도우미",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 커스텀 CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        background: linear-gradient(90deg, #FF6B6B, #4ECDC4);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        text-align: center;
        padding: 1rem 0;
    }
    .sub-header {
        text-align: center;
        color: #666;
        margin-bottom: 2rem;
    }
    .metric-card {
        background: #f8f9fa;
        padding: 1rem;
        border-radius: 10px;
        border-left: 4px solid #4ECDC4;
    }
    .warning-box {
        background: #fff3cd;
        padding: 1rem;
        border-radius: 10px;
        border-left: 4px solid #ffc107;
    }
    .success-box {
        background: #d4edda;
        padding: 1rem;
        border-radius: 10px;
        border-left: 4px solid #28a745;
    }
</style>
""", unsafe_allow_html=True)


# ============ 카테고리 & 구조 정의 ============

CATEGORIES = {
    "자기계발": {
        "id": "22",
        "keywords": ["성공", "습관", "독서", "생산성", "마인드셋", "동기부여", "목표", "시간관리"],
        "style": "동기부여형, 실용적 팁 제공",
        "target": "20-40대 직장인, 대학생"
    },
    "역사": {
        "id": "27",
        "keywords": ["역사", "한국사", "세계사", "전쟁", "인물", "문명", "왕조", "사건"],
        "style": "스토리텔링형, 드라마틱한 전개",
        "target": "역사에 관심 있는 전연령"
    },
    "과학": {
        "id": "28",
        "keywords": ["과학", "우주", "물리", "생물", "기술", "발명", "연구", "실험"],
        "style": "호기심 유발형, 쉬운 설명",
        "target": "과학에 관심 있는 10-40대"
    },
    "경제/시사": {
        "id": "25",
        "keywords": ["경제", "주식", "부동산", "금리", "정책", "국제", "트렌드", "분석"],
        "style": "분석형, 인사이트 제공",
        "target": "경제/시사에 관심 있는 20-50대"
    },
    "IT/기술": {
        "id": "28",
        "keywords": ["AI", "프로그래밍", "스타트업", "앱", "소프트웨어", "IT", "개발", "테크"],
        "style": "트렌드 분석형, 실용 정보",
        "target": "IT 관심 있는 20-40대"
    },
    "건강/라이프": {
        "id": "26",
        "keywords": ["건강", "운동", "다이어트", "식단", "수면", "멘탈", "웰빙", "루틴"],
        "style": "정보 전달형, 실천 가이드",
        "target": "건강 관심 있는 전연령"
    },
    "육아/교육": {
        "id": "22",
        "keywords": ["육아", "교육", "아이", "발달", "학습", "부모", "놀이", "성장"],
        "style": "공감형, 실용 팁 제공",
        "target": "영유아~초등 자녀를 둔 부모"
    }
}

VIDEO_STRUCTURES = {
    "숏폼 (1분)": {
        "total_seconds": 60,
        "structure": [
            {"type": "hook", "duration": 5, "description": "강력한 훅"},
            {"type": "content", "duration": 45, "description": "핵심 내용"},
            {"type": "cta", "duration": 10, "description": "구독 유도"}
        ]
    },
    "미드폼 (5분)": {
        "total_seconds": 300,
        "structure": [
            {"type": "hook", "duration": 15, "description": "훅 + 미리보기"},
            {"type": "intro", "duration": 20, "description": "주제 소개"},
            {"type": "content_1", "duration": 80, "description": "핵심 포인트 1"},
            {"type": "content_2", "duration": 80, "description": "핵심 포인트 2"},
            {"type": "content_3", "duration": 60, "description": "핵심 포인트 3"},
            {"type": "summary", "duration": 25, "description": "요약"},
            {"type": "cta", "duration": 20, "description": "구독 유도"}
        ]
    },
    "롱폼 (10분)": {
        "total_seconds": 600,
        "structure": [
            {"type": "hook", "duration": 20, "description": "강력한 훅"},
            {"type": "intro", "duration": 40, "description": "주제 소개"},
            {"type": "content_1", "duration": 120, "description": "핵심 포인트 1"},
            {"type": "content_2", "duration": 120, "description": "핵심 포인트 2"},
            {"type": "content_3", "duration": 120, "description": "핵심 포인트 3"},
            {"type": "deep_dive", "duration": 80, "description": "심층 분석"},
            {"type": "summary", "duration": 40, "description": "요약"},
            {"type": "cta", "duration": 30, "description": "구독 유도"},
            {"type": "outro", "duration": 30, "description": "다음 예고"}
        ]
    },
    "롱폼 (15분+)": {
        "total_seconds": 900,
        "structure": [
            {"type": "cold_open", "duration": 15, "description": "콜드 오픈"},
            {"type": "hook", "duration": 25, "description": "훅 + 미리보기"},
            {"type": "intro", "duration": 50, "description": "배경 설명"},
            {"type": "content_1", "duration": 150, "description": "챕터 1"},
            {"type": "content_2", "duration": 150, "description": "챕터 2"},
            {"type": "content_3", "duration": 150, "description": "챕터 3"},
            {"type": "content_4", "duration": 120, "description": "챕터 4"},
            {"type": "analysis", "duration": 100, "description": "종합 분석"},
            {"type": "takeaway", "duration": 60, "description": "실천 포인트"},
            {"type": "summary", "duration": 40, "description": "핵심 요약"},
            {"type": "cta", "duration": 40, "description": "구독 유도"}
        ]
    }
}


# ============ 유틸리티 함수 ============

def estimate_speech_duration(text: str, wpm: int = 150) -> float:
    """텍스트 읽기 시간 추정 (초)"""
    korean_chars = len(re.findall(r'[가-힣]', text))
    other_chars = len(text) - korean_chars
    korean_minutes = korean_chars / 300
    other_minutes = (other_chars / 5) / wpm
    return (korean_minutes + other_minutes) * 60


def format_duration(seconds: float) -> str:
    """초를 MM:SS 형식으로 변환"""
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes}:{secs:02d}"


def get_api_keys():
    """API 키 가져오기 (환경변수 또는 세션)"""
    # 환경변수에서 먼저 확인 (Streamlit Cloud secrets)
    anthropic_key = os.getenv("ANTHROPIC_API_KEY", "") or st.session_state.get("anthropic_key", "")
    youtube_key = os.getenv("YOUTUBE_API_KEY", "") or st.session_state.get("youtube_key", "")
    
    return anthropic_key, youtube_key


# ============ 트렌드 분석 클래스 ============

class TrendAnalyzer:
    """트렌드 분석기"""
    
    def __init__(self, youtube_api_key: str = None, anthropic_api_key: str = None):
        self.youtube_api_key = youtube_api_key
        self.anthropic_api_key = anthropic_api_key
        
        if youtube_api_key and YOUTUBE_API_AVAILABLE:
            try:
                self.youtube = build("youtube", "v3", developerKey=youtube_api_key)
            except Exception as e:
                self.youtube = None
                st.error(f"YouTube API 초기화 실패: {e}")
        else:
            self.youtube = None
            
        if anthropic_api_key and ANTHROPIC_AVAILABLE:
            self.claude = anthropic.Anthropic(api_key=anthropic_api_key)
        else:
            self.claude = None
            
        if PYTRENDS_AVAILABLE:
            try:
                self.pytrends = TrendReq(hl='ko-KR', tz=540)
            except:
                self.pytrends = None
        else:
            self.pytrends = None
    
    def search_trending_videos(self, category: str, max_results: int = 15) -> List[Dict]:
        """카테고리별 트렌딩 영상 검색"""
        if not self.youtube:
            return []
        
        category_info = CATEGORIES.get(category, {})
        keywords = category_info.get("keywords", [])
        all_videos = []
        
        # 인기 영상 조회
        try:
            trending_response = self.youtube.videos().list(
                part="snippet,statistics,contentDetails",
                chart="mostPopular",
                regionCode="KR",
                videoCategoryId=category_info.get("id", "22"),
                maxResults=min(max_results, 10)
            ).execute()
            
            for item in trending_response.get("items", []):
                all_videos.append(self._parse_video_item(item))
        except Exception as e:
            st.warning(f"인기 영상 조회 실패: {e}")
        
        # 키워드별 검색
        for keyword in keywords[:2]:
            try:
                search_response = self.youtube.search().list(
                    part="snippet",
                    q=keyword,
                    type="video",
                    order="viewCount",
                    publishedAfter=(datetime.now() - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    regionCode="KR",
                    maxResults=5
                ).execute()
                
                video_ids = [item["id"]["videoId"] for item in search_response.get("items", [])]
                
                if video_ids:
                    stats_response = self.youtube.videos().list(
                        part="snippet,statistics,contentDetails",
                        id=",".join(video_ids)
                    ).execute()
                    
                    for item in stats_response.get("items", []):
                        all_videos.append(self._parse_video_item(item))
                        
            except Exception as e:
                continue
        
        # 중복 제거
        seen = set()
        unique_videos = []
        for v in all_videos:
            if v["video_id"] not in seen:
                seen.add(v["video_id"])
                unique_videos.append(v)
        
        return sorted(unique_videos, key=lambda x: x.get("views", 0), reverse=True)[:max_results]
    
    def _parse_video_item(self, item: Dict) -> Dict:
        """영상 아이템 파싱"""
        snippet = item.get("snippet", {})
        stats = item.get("statistics", {})
        
        video_id = item.get("id")
        if isinstance(video_id, dict):
            video_id = video_id.get("videoId", "")
        
        return {
            "video_id": video_id,
            "title": snippet.get("title", ""),
            "channel": snippet.get("channelTitle", ""),
            "description": snippet.get("description", "")[:200],
            "published_at": snippet.get("publishedAt", ""),
            "views": int(stats.get("viewCount", 0)),
            "likes": int(stats.get("likeCount", 0)),
            "comments": int(stats.get("commentCount", 0)),
            "thumbnail": snippet.get("thumbnails", {}).get("high", {}).get("url", "")
        }
    
    def get_keyword_trends(self, keywords: List[str]) -> Dict:
        """키워드 트렌드"""
        if not self.pytrends:
            return {"error": "Google Trends를 사용할 수 없습니다.", "rising_keywords": []}
        
        try:
            self.pytrends.build_payload(keywords[:5], cat=0, timeframe='today 3-m', geo='KR')
            related_queries = self.pytrends.related_queries()
            
            rising_keywords = []
            for kw in keywords[:5]:
                if kw in related_queries and related_queries[kw].get("rising") is not None:
                    rising = related_queries[kw]["rising"]
                    if not rising.empty:
                        rising_keywords.extend(rising["query"].tolist()[:5])
            
            return {
                "keywords": keywords,
                "rising_keywords": list(set(rising_keywords))[:15]
            }
        except Exception as e:
            return {"error": str(e), "rising_keywords": []}
    
    def predict_views(self, title: str, category: str, competitor_avg: int = 10000) -> Dict:
        """조회수 예측"""
        score = 50
        factors = []
        
        title_len = len(title)
        if 30 <= title_len <= 60:
            score += 10
            factors.append("✅ 적절한 제목 길이")
        elif title_len > 80:
            score -= 10
            factors.append("⚠️ 제목이 너무 김")
        
        if re.search(r'\d+', title):
            score += 10
            factors.append("✅ 숫자 포함")
        
        emotion_words = ["충격", "놀라운", "최고", "비밀", "진실", "반전", "필수", "꼭", "드디어", "결국"]
        if any(word in title for word in emotion_words):
            score += 15
            factors.append("✅ 감정 유발 키워드")
        
        if "?" in title or title.endswith("까") or title.endswith("요"):
            score += 5
            factors.append("✅ 질문/대화형 제목")
        
        predicted_views = int(competitor_avg * (score / 50))
        
        return {
            "score": min(score, 100),
            "predicted_views": predicted_views,
            "predicted_views_range": f"{int(predicted_views * 0.5):,} ~ {int(predicted_views * 1.5):,}",
            "factors": factors,
            "grade": "🔥 높음" if score >= 70 else "👍 중간" if score >= 50 else "😐 낮음"
        }
    
    def generate_ai_insights(self, category: str, trending_videos: List[Dict]) -> str:
        """AI 인사이트 생성"""
        if not self.claude:
            return "⚠️ Anthropic API 키가 없어 AI 분석을 사용할 수 없습니다."
        
        prompt = f"""
유튜브 콘텐츠 전략 전문가로서 아래 데이터를 분석해주세요.

## 카테고리: {category}

## 현재 트렌딩 영상 TOP 10
{json.dumps(trending_videos[:10], ensure_ascii=False, indent=2)}

## 분석 요청
1. **현재 트렌드 요약**: 어떤 주제가 인기인가요?
2. **성공 패턴**: 조회수 높은 영상의 공통점 (제목, 주제)
3. **추천 콘텐츠 아이디어 5개**: 구체적인 제목까지 제안
4. **차별화 전략**: 경쟁에서 이기려면?

한국어로 실용적인 인사이트를 제공해주세요. 각 섹션을 명확히 구분해주세요.
"""
        
        try:
            response = self.claude.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=1500,
                messages=[{"role": "user", "content": prompt}]
            )
            return response.content[0].text
        except Exception as e:
            return f"⚠️ AI 분석 중 오류: {str(e)}"


# ============ 대본 생성 클래스 ============

class ScriptGenerator:
    """대본 생성기"""
    
    def __init__(self, anthropic_api_key: str = None):
        if anthropic_api_key and ANTHROPIC_AVAILABLE:
            self.claude = anthropic.Anthropic(api_key=anthropic_api_key)
        else:
            self.claude = None
    
    def generate_script(
        self,
        topic: str,
        category: str,
        video_length: str,
        competitor_titles: List[str] = None,
        keywords: List[str] = None,
        style_notes: str = ""
    ) -> Dict:
        """대본 생성"""
        
        if not self.claude:
            return {"error": "Anthropic API 키가 필요합니다."}
        
        category_info = CATEGORIES.get(category, {})
        structure = VIDEO_STRUCTURES.get(video_length, VIDEO_STRUCTURES["미드폼 (5분)"])
        
        competitor_context = ""
        if competitor_titles:
            competitor_context = f"""
## 경쟁 영상 제목 (벤치마킹)
{chr(10).join(f'- {t}' for t in competitor_titles[:8])}
"""
        
        keyword_context = ""
        if keywords:
            keyword_context = f"""
## SEO 타겟 키워드
{', '.join(keywords[:10])}
"""
        
        prompt = f"""
유튜브 정보성 콘텐츠 전문 작가입니다. 아래 조건에 맞는 영상 대본을 작성해주세요.

## 주제
{topic}

## 카테고리: {category}
- 타겟 시청자: {category_info.get('target', '일반 대중')}
- 스타일: {category_info.get('style', '정보 전달형')}

## 영상 길이: {video_length} (총 {structure['total_seconds']}초)
{competitor_context}
{keyword_context}

## 추가 요청: {style_notes if style_notes else '없음'}

## 대본 구조
{json.dumps(structure['structure'], ensure_ascii=False, indent=2)}

## 응답 형식 (반드시 JSON)
{{
    "seo": {{
        "title_options": ["제목1 (50자 이내)", "제목2", "제목3"],
        "description": "영상 설명 (300자)",
        "tags": ["태그1", "태그2", "태그3", "태그4", "태그5"],
        "hashtags": ["#해시태그1", "#해시태그2", "#해시태그3"]
    }},
    "hooks": {{
        "hook_1": "충격적 사실형 훅 (한 문장)",
        "hook_2": "질문형 훅 (한 문장)",
        "hook_3": "스토리형 훅 (한 문장)"
    }},
    "scenes": [
        {{
            "scene_number": 1,
            "scene_type": "hook",
            "target_duration": 15,
            "narration": "나레이션 전문 (target_duration에 맞게, 한글 기준 분당 300자)",
            "on_screen_text": "화면에 띄울 핵심 텍스트",
            "visual_note": "어떤 이미지/영상이 필요한지"
        }}
    ],
    "key_messages": ["핵심 메시지1", "핵심 메시지2", "핵심 메시지3"]
}}

중요:
1. 각 장면 나레이션은 target_duration에 맞춰 작성 (한글 분당 300자 기준)
2. 훅은 5초 안에 시청자를 사로잡아야 함
3. SEO 제목은 핵심 키워드를 앞에 배치
4. JSON만 반환 (다른 텍스트 없이)
"""
        
        try:
            response = self.claude.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=4000,
                messages=[{"role": "user", "content": prompt}]
            )
            
            content = response.content[0].text
            
            # JSON 파싱
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            
            script_data = json.loads(content.strip())
            
            # 읽기 시간 계산
            total_duration = 0
            for scene in script_data.get("scenes", []):
                narration = scene.get("narration", "")
                estimated = estimate_speech_duration(narration)
                scene["estimated_duration"] = round(estimated, 1)
                scene["duration_display"] = format_duration(estimated)
                total_duration += estimated
            
            script_data["total_duration"] = round(total_duration, 1)
            script_data["total_display"] = format_duration(total_duration)
            
            return script_data
            
        except json.JSONDecodeError as e:
            return {"error": f"JSON 파싱 오류: {str(e)}", "raw": content if 'content' in dir() else ""}
        except Exception as e:
            return {"error": str(e)}


# ============ 메인 UI ============

def main():
    # 헤더
    st.markdown('<h1 class="main-header">🎬 YouTube 콘텐츠 제작 도우미</h1>', unsafe_allow_html=True)
    st.markdown('<p class="sub-header">AI 기반 트렌드 분석 + 대본 자동 생성</p>', unsafe_allow_html=True)
    
    # 사이드바
    with st.sidebar:
        st.header("⚙️ 설정")
        
        # API 키 입력
        st.subheader("🔑 API 키")
        
        # 환경변수에서 가져오기 시도
        default_anthropic = os.getenv("ANTHROPIC_API_KEY", "")
        default_youtube = os.getenv("YOUTUBE_API_KEY", "")
        
        anthropic_key = st.text_input(
            "Anthropic API Key",
            value=default_anthropic,
            type="password",
            help="대본 생성에 필요"
        )
        
        youtube_key = st.text_input(
            "YouTube API Key", 
            value=default_youtube,
            type="password",
            help="트렌드 분석에 필요"
        )
        
        # 세션에 저장
        st.session_state["anthropic_key"] = anthropic_key
        st.session_state["youtube_key"] = youtube_key
        
        st.divider()
        
        # 카테고리 선택
        st.subheader("📂 콘텐츠 설정")
        selected_category = st.selectbox(
            "카테고리",
            list(CATEGORIES.keys()),
            help="채널의 주요 카테고리"
        )
        
        video_length = st.selectbox(
            "영상 길이",
            list(VIDEO_STRUCTURES.keys()),
            index=1
        )
        
        st.divider()
        
        # API 상태 표시
        st.subheader("📡 연결 상태")
        if anthropic_key:
            st.success("✅ Anthropic 연결됨")
        else:
            st.warning("⚠️ Anthropic 키 필요")
            
        if youtube_key:
            st.success("✅ YouTube 연결됨")
        else:
            st.warning("⚠️ YouTube 키 필요")
    
    # 메인 탭
    tab1, tab2, tab3 = st.tabs(["📈 트렌드 분석", "📝 대본 생성", "📥 내보내기"])
    
    # ============ 탭 1: 트렌드 분석 ============
    with tab1:
        st.header("📈 트렌드 분석")
        
        if not youtube_key:
            st.warning("👈 사이드바에서 YouTube API 키를 입력해주세요.")
            st.info("""
            **YouTube API 키 발급 방법:**
            1. [Google Cloud Console](https://console.cloud.google.com/) 접속
            2. 새 프로젝트 생성
            3. "YouTube Data API v3" 검색 후 활성화
            4. 사용자 인증 정보 > API 키 생성
            """)
        else:
            col1, col2 = st.columns([3, 1])
            
            with col1:
                st.info(f"🎯 **{selected_category}** 카테고리의 트렌드를 분석합니다.")
            
            with col2:
                analyze_btn = st.button("🔍 분석 시작", type="primary", use_container_width=True)
            
            if analyze_btn:
                analyzer = TrendAnalyzer(youtube_key, anthropic_key)
                
                with st.spinner("트렌드 데이터 수집 중..."):
                    # 트렌딩 영상
                    trending = analyzer.search_trending_videos(selected_category)
                    st.session_state["trending_videos"] = trending
                    
                    # 키워드 트렌드
                    keywords = CATEGORIES[selected_category]["keywords"]
                    keyword_data = analyzer.get_keyword_trends(keywords)
                    st.session_state["keyword_data"] = keyword_data
                
                st.success(f"✅ {len(trending)}개 영상 분석 완료!")
            
            # 결과 표시
            if "trending_videos" in st.session_state and st.session_state["trending_videos"]:
                trending = st.session_state["trending_videos"]
                
                st.subheader("🔥 인기 영상 TOP 10")
                
                for i, video in enumerate(trending[:10], 1):
                    with st.expander(f"{i}. {video['title'][:60]}... ({video['views']:,}회)"):
                        col1, col2 = st.columns([1, 2])
                        
                        with col1:
                            if video.get("thumbnail"):
                                st.image(video["thumbnail"], use_container_width=True)
                        
                        with col2:
                            st.write(f"**채널:** {video['channel']}")
                            st.write(f"**조회수:** {video['views']:,}")
                            st.write(f"**좋아요:** {video['likes']:,}")
                            st.write(f"**게시일:** {video['published_at'][:10]}")
                            
                            # 벤치마킹 체크박스
                            if st.checkbox(f"벤치마킹 선택", key=f"bench_{i}"):
                                if "benchmark_titles" not in st.session_state:
                                    st.session_state["benchmark_titles"] = []
                                if video["title"] not in st.session_state["benchmark_titles"]:
                                    st.session_state["benchmark_titles"].append(video["title"])
                
                # 상승 키워드
                if "keyword_data" in st.session_state:
                    keyword_data = st.session_state["keyword_data"]
                    if keyword_data.get("rising_keywords"):
                        st.subheader("📈 상승 키워드")
                        st.write(" | ".join([f"`{kw}`" for kw in keyword_data["rising_keywords"][:10]]))
                
                # AI 인사이트
                if anthropic_key:
                    if st.button("🤖 AI 인사이트 받기"):
                        analyzer = TrendAnalyzer(youtube_key, anthropic_key)
                        with st.spinner("AI가 분석 중..."):
                            insights = analyzer.generate_ai_insights(selected_category, trending)
                        st.subheader("💡 AI 인사이트")
                        st.markdown(insights)
    
    # ============ 탭 2: 대본 생성 ============
    with tab2:
        st.header("📝 대본 생성")
        
        if not anthropic_key:
            st.warning("👈 사이드바에서 Anthropic API 키를 입력해주세요.")
            st.info("""
            **Anthropic API 키 발급 방법:**
            1. [Anthropic Console](https://console.anthropic.com/) 접속
            2. 회원가입/로그인
            3. API Keys > Create Key
            """)
        else:
            # 주제 입력
            topic = st.text_input(
                "🎯 영상 주제",
                placeholder="예: 2024년 AI가 바꿀 10가지 직업의 미래",
                help="구체적일수록 좋은 대본이 나옵니다"
            )
            
            # 고급 옵션
            with st.expander("⚙️ 고급 옵션"):
                col1, col2 = st.columns(2)
                
                with col1:
                    target_keywords = st.text_input(
                        "SEO 키워드 (쉼표 구분)",
                        placeholder="AI, 직업, 미래, 자동화"
                    )
                
                with col2:
                    style_notes = st.text_input(
                        "스타일 요청",
                        placeholder="예: 유머러스하게, 사례 중심으로"
                    )
                
                # 벤치마킹 선택
                benchmark_titles = st.session_state.get("benchmark_titles", [])
                if benchmark_titles:
                    st.write("**선택된 벤치마킹 영상:**")
                    for title in benchmark_titles[:5]:
                        st.write(f"- {title[:50]}...")
            
            # 생성 버튼
            if st.button("✨ 대본 생성", type="primary", use_container_width=True):
                if not topic:
                    st.warning("주제를 입력해주세요.")
                else:
                    generator = ScriptGenerator(anthropic_key)
                    
                    keywords = CATEGORIES[selected_category]["keywords"]
                    if target_keywords:
                        keywords = [k.strip() for k in target_keywords.split(",")] + keywords
                    
                    with st.spinner("AI가 대본 작성 중... (30초~1분)"):
                        script = generator.generate_script(
                            topic=topic,
                            category=selected_category,
                            video_length=video_length,
                            competitor_titles=benchmark_titles,
                            keywords=keywords,
                            style_notes=style_notes
                        )
                    
                    if "error" in script:
                        st.error(f"오류: {script['error']}")
                    else:
                        st.session_state["generated_script"] = script
                        st.success("✅ 대본 생성 완료!")
            
            # 생성된 대본 표시
            if "generated_script" in st.session_state:
                script = st.session_state["generated_script"]
                
                if "error" not in script:
                    # SEO 섹션
                    st.subheader("🔍 SEO 최적화")
                    seo = script.get("seo", {})
                    
                    st.write("**제목 옵션:**")
                    for i, title in enumerate(seo.get("title_options", []), 1):
                        col1, col2 = st.columns([4, 1])
                        with col1:
                            st.code(title)
                        with col2:
                            if youtube_key:
                                analyzer = TrendAnalyzer(youtube_key)
                                pred = analyzer.predict_views(title, selected_category)
                                st.write(pred["grade"])
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        st.write("**태그:**")
                        st.write(", ".join(seo.get("tags", [])))
                    with col2:
                        st.write("**해시태그:**")
                        st.write(" ".join(seo.get("hashtags", [])))
                    
                    # 훅 섹션
                    st.subheader("🎣 훅 옵션 (첫 5초)")
                    hooks = script.get("hooks", {})
                    
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.info(f"**충격형**\n\n{hooks.get('hook_1', '')}")
                    with col2:
                        st.info(f"**질문형**\n\n{hooks.get('hook_2', '')}")
                    with col3:
                        st.info(f"**스토리형**\n\n{hooks.get('hook_3', '')}")
                    
                    # 장면별 대본
                    st.subheader("🎬 장면별 대본")
                    
                    target_total = VIDEO_STRUCTURES[video_length]["total_seconds"]
                    actual_total = script.get("total_duration", 0)
                    
                    col1, col2, col3 = st.columns(3)
                    col1.metric("목표 길이", format_duration(target_total))
                    col2.metric("예상 길이", script.get("total_display", "N/A"))
                    col3.metric("차이", f"{actual_total - target_total:+.0f}초")
                    
                    for scene in script.get("scenes", []):
                        target_dur = scene.get("target_duration", 0)
                        actual_dur = scene.get("estimated_duration", 0)
                        diff = actual_dur - target_dur
                        
                        status = "🟢" if abs(diff) <= 5 else ("🟡" if abs(diff) <= 10 else "🔴")
                        
                        with st.expander(
                            f"{status} 장면 {scene['scene_number']}: {scene['scene_type'].upper()} "
                            f"({scene.get('duration_display', 'N/A')} / 목표 {target_dur}초)"
                        ):
                            st.text_area(
                                "나레이션",
                                value=scene.get("narration", ""),
                                height=120,
                                key=f"narr_{scene['scene_number']}"
                            )
                            
                            col1, col2 = st.columns(2)
                            with col1:
                                st.write("**화면 텍스트:**")
                                st.code(scene.get("on_screen_text", "-"))
                            with col2:
                                st.write("**시각 연출:**")
                                st.write(scene.get("visual_note", "-"))
                            
                            if abs(diff) > 5:
                                if diff > 0:
                                    st.warning(f"⚠️ {diff:.0f}초 초과 - 나레이션을 줄여주세요")
                                else:
                                    st.info(f"ℹ️ {abs(diff):.0f}초 여유 - 내용 추가 가능")
                    
                    # 핵심 메시지
                    st.subheader("💡 핵심 메시지")
                    for msg in script.get("key_messages", []):
                        st.write(f"• {msg}")
    
    # ============ 탭 3: 내보내기 ============
    with tab3:
        st.header("📥 결과 내보내기")
        
        if "generated_script" not in st.session_state:
            st.info("먼저 '대본 생성' 탭에서 대본을 생성해주세요.")
        else:
            script = st.session_state["generated_script"]
            
            if "error" not in script:
                # JSON 다운로드
                col1, col2 = st.columns(2)
                
                with col1:
                    json_str = json.dumps(script, ensure_ascii=False, indent=2)
                    st.download_button(
                        "📄 JSON 다운로드",
                        json_str,
                        file_name=f"script_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                        mime="application/json",
                        use_container_width=True
                    )
                
                # 텍스트 형식
                with col2:
                    full_script = []
                    seo = script.get("seo", {})
                    titles = seo.get("title_options", ["제목 없음"])
                    
                    full_script.append(f"# {titles[0]}\n")
                    full_script.append(f"카테고리: {selected_category}")
                    full_script.append(f"예상 길이: {script.get('total_display', 'N/A')}\n")
                    full_script.append(f"태그: {', '.join(seo.get('tags', []))}\n")
                    full_script.append("---\n")
                    
                    for scene in script.get("scenes", []):
                        full_script.append(f"## [{scene['scene_type'].upper()}] 장면 {scene['scene_number']}")
                        full_script.append(f"시간: {scene.get('duration_display', 'N/A')} (목표: {scene.get('target_duration', 0)}초)\n")
                        full_script.append(f"### 나레이션\n{scene.get('narration', '')}\n")
                        full_script.append(f"**화면 텍스트:** {scene.get('on_screen_text', '-')}")
                        full_script.append(f"**시각 연출:** {scene.get('visual_note', '-')}\n")
                        full_script.append("---\n")
                    
                    full_text = "\n".join(full_script)
                    
                    st.download_button(
                        "📝 텍스트 다운로드",
                        full_text,
                        file_name=f"script_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                        mime="text/plain",
                        use_container_width=True
                    )
                
                # 미리보기
                st.subheader("📋 전체 대본 미리보기")
                st.text_area("", full_text, height=400)


if __name__ == "__main__":
    main()
