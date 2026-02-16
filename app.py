"""
🎬 YouTube 콘텐츠 제작 도우미 v3.0
트렌드 분석 + 대본 생성 (업그레이드 버전)

주요 기능:
- 언어/지역별 필터
- Google Trends 연동 (급상승 키워드)
- 기간별 인기 검색어/영상
- 경쟁 채널 분석
- 영상 세부 분석 (좋아요율, 댓글율, 업로드 패턴 등)
- 벤치마킹 기능
"""
import streamlit as st
import json
import os
import re
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from collections import Counter
import pandas as pd

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
    page_title="YouTube 콘텐츠 제작 도우미 v3",
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
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1rem;
        border-radius: 10px;
        color: white;
        text-align: center;
    }
    .trend-up { color: #00C851; font-weight: bold; }
    .trend-down { color: #ff4444; font-weight: bold; }
    .keyword-tag {
        display: inline-block;
        background: #e3f2fd;
        padding: 0.3rem 0.8rem;
        border-radius: 15px;
        margin: 0.2rem;
        font-size: 0.9rem;
    }
    .video-card {
        border: 1px solid #eee;
        border-radius: 10px;
        padding: 1rem;
        margin: 0.5rem 0;
    }
</style>
""", unsafe_allow_html=True)


# ============ 상수 정의 ============

# 언어/지역 설정
REGIONS = {
    "한국어": {
        "countries": {"한국": "KR"},
        "language": "ko",
        "trends_geo": "KR",
        "trends_pn": "south_korea"
    },
    "영어": {
        "countries": {"미국": "US", "영국": "GB", "호주": "AU", "캐나다": "CA"},
        "language": "en",
        "trends_geo": "US",
        "trends_pn": "united_states"
    },
    "일본어": {
        "countries": {"일본": "JP"},
        "language": "ja",
        "trends_geo": "JP",
        "trends_pn": "japan"
    },
    "스페인어": {
        "countries": {"스페인": "ES", "멕시코": "MX", "아르헨티나": "AR"},
        "language": "es",
        "trends_geo": "ES",
        "trends_pn": "spain"
    },
    "중국어 (번체)": {
        "countries": {"대만": "TW", "홍콩": "HK"},
        "language": "zh-TW",
        "trends_geo": "TW",
        "trends_pn": "taiwan"
    },
    "포르투갈어": {
        "countries": {"브라질": "BR", "포르투갈": "PT"},
        "language": "pt",
        "trends_geo": "BR",
        "trends_pn": "brazil"
    },
    "프랑스어": {
        "countries": {"프랑스": "FR", "캐나다 (퀘벡)": "CA"},
        "language": "fr",
        "trends_geo": "FR",
        "trends_pn": "france"
    },
    "독일어": {
        "countries": {"독일": "DE", "오스트리아": "AT"},
        "language": "de",
        "trends_geo": "DE",
        "trends_pn": "germany"
    }
}

# 카테고리 (YouTube 공식 카테고리 ID)
CATEGORIES = {
    "전체": None,
    "엔터테인먼트": "24",
    "음악": "10",
    "게임": "20",
    "스포츠": "17",
    "뉴스/정치": "25",
    "교육": "27",
    "과학/기술": "28",
    "여행/이벤트": "19",
    "인물/블로그": "22",
    "코미디": "23",
    "영화/애니메이션": "1",
    "자동차": "2",
    "하우투/스타일": "26",
    "비영리/사회운동": "29",
    "동물": "15"
}

# 기간 설정
TIME_PERIODS = {
    "어제": 1,
    "최근 3일": 3,
    "최근 7일": 7,
    "최근 30일": 30,
    "최근 90일": 90
}

# Google Trends 기간 매핑
TRENDS_TIMEFRAMES = {
    "어제": "now 1-d",
    "최근 3일": "now 4-d",
    "최근 7일": "now 7-d",
    "최근 30일": "today 1-m",
    "최근 90일": "today 3-m"
}

# 국가 코드 → Trends pn 매핑
COUNTRY_TO_PN = {
    "KR": "south_korea", "US": "united_states", "GB": "united_kingdom",
    "JP": "japan", "ES": "spain", "MX": "mexico", "BR": "brazil",
    "FR": "france", "DE": "germany", "TW": "taiwan", "CA": "canada",
    "AU": "australia", "AR": "argentina", "PT": "portugal", "AT": "austria",
    "HK": "hong_kong"
}


# ============ 유틸리티 함수 ============

def format_number(num: int) -> str:
    """숫자를 읽기 쉬운 형식으로 변환"""
    if num >= 1_000_000_000:
        return f"{num/1_000_000_000:.1f}B"
    elif num >= 1_000_000:
        return f"{num/1_000_000:.1f}M"
    elif num >= 1_000:
        return f"{num/1_000:.1f}K"
    return str(num)


def parse_duration(duration: str) -> int:
    """ISO 8601 기간을 초로 변환"""
    if not duration:
        return 0
    match = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', duration)
    if not match:
        return 0
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    seconds = int(match.group(3) or 0)
    return hours * 3600 + minutes * 60 + seconds


def format_duration(seconds: int) -> str:
    """초를 MM:SS 또는 HH:MM:SS 형식으로 변환"""
    if seconds >= 3600:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        return f"{hours}:{minutes:02d}:{secs:02d}"
    else:
        minutes = seconds // 60
        secs = seconds % 60
        return f"{minutes}:{secs:02d}"


def extract_keywords(titles: List[str], top_n: int = 20) -> List[Tuple[str, int]]:
    """제목들에서 키워드 추출"""
    stopwords = {'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been', 
                 'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
                 'would', 'could', 'should', 'to', 'of', 'in', 'for', 'on', 
                 'with', 'at', 'by', 'from', 'or', 'and', 'but', 'not', 
                 'this', 'that', 'it', 'its', 'i', 'me', 'my', 'we', 'our', 
                 'you', 'your', 'he', 'she', 'they', 'them', 'his', 'her',
                 '이', '그', '저', '것', '수', '등', '및', '을', '를', '에', 
                 '의', '가', '은', '는', '으로', '로', '에서', '와', '과', '도',
                 '만', '에게', '한', '하는', '있는', '없는', '된', '되는', '더'}
    
    all_words = []
    for title in titles:
        cleaned = re.sub(r'[^\w\s가-힣]', ' ', title.lower())
        words = cleaned.split()
        words = [w for w in words if len(w) >= 2 and w not in stopwords]
        all_words.extend(words)
    
    return Counter(all_words).most_common(top_n)


def analyze_title_pattern(title: str) -> Dict:
    """제목 패턴 분석"""
    patterns = {
        "has_number": bool(re.search(r'\d+', title)),
        "has_question": '?' in title or title.endswith('까') or title.endswith('요'),
        "has_emoji": bool(re.search(r'[^\w\s가-힣a-zA-Z0-9.,!?\'"-]', title)),
        "has_bracket": bool(re.search(r'[\[\]【】\(\)]', title)),
        "length": len(title),
        "word_count": len(title.split())
    }
    
    emotion_keywords = ['충격', '놀라운', '최고', '비밀', '진실', '반전', '필수', '꼭', 
                       '드디어', '결국', '실화', '레전드', 'ㄷㄷ', 'ㅋㅋ', '대박', '미쳤',
                       'shocking', 'amazing', 'best', 'secret', 'truth', 'must', 'wow']
    patterns["has_emotion"] = any(kw in title.lower() for kw in emotion_keywords)
    
    return patterns


def calculate_engagement(views: int, likes: int, comments: int) -> Dict:
    """참여율 계산"""
    if views == 0:
        return {"like_rate": 0, "comment_rate": 0, "engagement_rate": 0}
    
    like_rate = (likes / views) * 100
    comment_rate = (comments / views) * 100
    engagement_rate = ((likes + comments) / views) * 100
    
    return {
        "like_rate": round(like_rate, 2),
        "comment_rate": round(comment_rate, 4),
        "engagement_rate": round(engagement_rate, 2)
    }


# ============ YouTube API 클래스 ============

class YouTubeAnalyzer:
    """YouTube 분석기"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        if YOUTUBE_API_AVAILABLE and api_key:
            try:
                self.youtube = build("youtube", "v3", developerKey=api_key)
            except Exception as e:
                self.youtube = None
                st.error(f"YouTube API 초기화 실패: {e}")
        else:
            self.youtube = None
    
    def get_trending_videos(self, region_code: str = "KR", category_id: str = None, max_results: int = 50) -> List[Dict]:
        """인기 급상승 영상 조회"""
        if not self.youtube:
            return []
        
        try:
            params = {
                "part": "snippet,statistics,contentDetails",
                "chart": "mostPopular",
                "regionCode": region_code,
                "maxResults": min(max_results, 50)
            }
            if category_id:
                params["videoCategoryId"] = category_id
            
            response = self.youtube.videos().list(**params).execute()
            return [self._parse_video(item) for item in response.get("items", [])]
        except Exception as e:
            st.error(f"인기 영상 조회 오류: {e}")
            return []
    
    def search_videos(self, query: str, region_code: str = "KR", language: str = "ko",
                      published_after: datetime = None, max_results: int = 50, order: str = "viewCount") -> List[Dict]:
        """키워드로 영상 검색"""
        if not self.youtube:
            return []
        
        try:
            params = {
                "part": "snippet",
                "q": query,
                "type": "video",
                "regionCode": region_code,
                "relevanceLanguage": language,
                "order": order,
                "maxResults": min(max_results, 50)
            }
            if published_after:
                params["publishedAfter"] = published_after.strftime("%Y-%m-%dT%H:%M:%SZ")
            
            search_response = self.youtube.search().list(**params).execute()
            video_ids = [item["id"]["videoId"] for item in search_response.get("items", [])]
            
            if not video_ids:
                return []
            
            videos_response = self.youtube.videos().list(
                part="snippet,statistics,contentDetails",
                id=",".join(video_ids)
            ).execute()
            
            videos = [self._parse_video(item) for item in videos_response.get("items", [])]
            return sorted(videos, key=lambda x: x.get("views", 0), reverse=True)
        except Exception as e:
            st.error(f"검색 오류: {e}")
            return []
    
    def get_channel_info(self, channel_id: str) -> Dict:
        """채널 정보 조회"""
        if not self.youtube:
            return {}
        
        try:
            response = self.youtube.channels().list(
                part="snippet,statistics,contentDetails",
                id=channel_id
            ).execute()
            
            if not response.get("items"):
                return {}
            
            channel = response["items"][0]
            return {
                "id": channel["id"],
                "title": channel["snippet"]["title"],
                "description": channel["snippet"].get("description", "")[:200],
                "thumbnail": channel["snippet"]["thumbnails"].get("high", {}).get("url", ""),
                "subscribers": int(channel["statistics"].get("subscriberCount", 0)),
                "total_views": int(channel["statistics"].get("viewCount", 0)),
                "video_count": int(channel["statistics"].get("videoCount", 0)),
                "created_at": channel["snippet"].get("publishedAt", ""),
                "uploads_playlist": channel["contentDetails"]["relatedPlaylists"]["uploads"]
            }
        except Exception as e:
            st.error(f"채널 조회 오류: {e}")
            return {}
    
    def get_channel_videos(self, channel_id: str, max_results: int = 30) -> List[Dict]:
        """채널의 최근 영상 조회"""
        if not self.youtube:
            return []
        
        try:
            channel_info = self.get_channel_info(channel_id)
            if not channel_info:
                return []
            
            playlist_id = channel_info.get("uploads_playlist")
            if not playlist_id:
                return []
            
            playlist_response = self.youtube.playlistItems().list(
                part="snippet",
                playlistId=playlist_id,
                maxResults=min(max_results, 50)
            ).execute()
            
            video_ids = [item["snippet"]["resourceId"]["videoId"] for item in playlist_response.get("items", [])]
            
            if not video_ids:
                return []
            
            videos_response = self.youtube.videos().list(
                part="snippet,statistics,contentDetails",
                id=",".join(video_ids)
            ).execute()
            
            return [self._parse_video(item) for item in videos_response.get("items", [])]
        except Exception as e:
            st.error(f"채널 영상 조회 오류: {e}")
            return []
    
    def get_channel_id_from_url(self, url: str) -> Optional[str]:
        """URL에서 채널 ID 추출"""
        if not self.youtube:
            return None
        
        if "/channel/" in url:
            return url.split("/channel/")[1].split("/")[0].split("?")[0]
        
        if "/@" in url:
            handle = url.split("/@")[1].split("/")[0].split("?")[0]
            try:
                response = self.youtube.search().list(part="snippet", q=handle, type="channel", maxResults=1).execute()
                if response.get("items"):
                    return response["items"][0]["snippet"]["channelId"]
            except:
                pass
        
        if "/c/" in url:
            custom_name = url.split("/c/")[1].split("/")[0].split("?")[0]
            try:
                response = self.youtube.search().list(part="snippet", q=custom_name, type="channel", maxResults=1).execute()
                if response.get("items"):
                    return response["items"][0]["snippet"]["channelId"]
            except:
                pass
        
        return None
    
    def _parse_video(self, item: Dict) -> Dict:
        """영상 데이터 파싱"""
        snippet = item.get("snippet", {})
        stats = item.get("statistics", {})
        content = item.get("contentDetails", {})
        
        views = int(stats.get("viewCount", 0))
        likes = int(stats.get("likeCount", 0))
        comments = int(stats.get("commentCount", 0))
        duration_seconds = parse_duration(content.get("duration", ""))
        
        engagement = calculate_engagement(views, likes, comments)
        title = snippet.get("title", "")
        title_patterns = analyze_title_pattern(title)
        
        published_at = snippet.get("publishedAt", "")
        upload_datetime = None
        if published_at:
            try:
                upload_datetime = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
            except:
                pass
        
        return {
            "video_id": item.get("id") if isinstance(item.get("id"), str) else item.get("id", {}).get("videoId", ""),
            "title": title,
            "channel_title": snippet.get("channelTitle", ""),
            "channel_id": snippet.get("channelId", ""),
            "description": snippet.get("description", "")[:300],
            "thumbnail": snippet.get("thumbnails", {}).get("high", {}).get("url", ""),
            "published_at": published_at,
            "upload_datetime": upload_datetime,
            "upload_day": upload_datetime.strftime("%A") if upload_datetime else "",
            "upload_hour": upload_datetime.hour if upload_datetime else 0,
            "views": views,
            "likes": likes,
            "comments": comments,
            "duration_seconds": duration_seconds,
            "duration_formatted": format_duration(duration_seconds),
            "like_rate": engagement["like_rate"],
            "comment_rate": engagement["comment_rate"],
            "engagement_rate": engagement["engagement_rate"],
            "title_patterns": title_patterns
        }


# ============ Google Trends 클래스 ============

class TrendsAnalyzer:
    """Google Trends 분석기"""
    
    def __init__(self):
        if PYTRENDS_AVAILABLE:
            try:
                self.pytrends = TrendReq(hl='ko', tz=540, timeout=(10, 25))
            except:
                self.pytrends = None
        else:
            self.pytrends = None
    
    def get_trending_searches(self, country_code: str = "KR") -> List[str]:
        """실시간 급상승 검색어"""
        if not self.pytrends:
            return []
        
        pn = COUNTRY_TO_PN.get(country_code, "south_korea")
        
        try:
            trending = self.pytrends.trending_searches(pn=pn)
            return trending[0].tolist()[:20] if not trending.empty else []
        except Exception as e:
            return []
    
    def get_related_queries(self, keywords: List[str], geo: str = "KR", timeframe: str = "today 1-m") -> Dict:
        """관련 검색어 조회"""
        if not self.pytrends or not keywords:
            return {"rising": [], "top": []}
        
        try:
            self.pytrends.build_payload(keywords[:5], cat=0, timeframe=timeframe, geo=geo)
            related = self.pytrends.related_queries()
            
            result = {"rising": [], "top": []}
            for kw in keywords[:5]:
                if kw in related:
                    if related[kw].get("rising") is not None and not related[kw]["rising"].empty:
                        result["rising"].extend(related[kw]["rising"]["query"].tolist()[:10])
                    if related[kw].get("top") is not None and not related[kw]["top"].empty:
                        result["top"].extend(related[kw]["top"]["query"].tolist()[:10])
            
            result["rising"] = list(dict.fromkeys(result["rising"]))[:15]
            result["top"] = list(dict.fromkeys(result["top"]))[:15]
            return result
        except:
            return {"rising": [], "top": []}
    
    def get_interest_over_time(self, keywords: List[str], geo: str = "KR", timeframe: str = "today 1-m") -> pd.DataFrame:
        """시간별 관심도 추이"""
        if not self.pytrends or not keywords:
            return pd.DataFrame()
        
        try:
            self.pytrends.build_payload(keywords[:5], cat=0, timeframe=timeframe, geo=geo)
            return self.pytrends.interest_over_time()
        except:
            return pd.DataFrame()


# ============ 메인 UI ============

def main():
    st.markdown('<h1 class="main-header">🎬 YouTube 콘텐츠 제작 도우미 v3.0</h1>', unsafe_allow_html=True)
    st.markdown('<p style="text-align:center;color:#666;">글로벌 트렌드 분석 + AI 대본 생성 + 경쟁 채널 분석</p>', unsafe_allow_html=True)
    
    # ============ 사이드바 ============
    with st.sidebar:
        st.header("⚙️ 설정")
        
        # API 키
        st.subheader("🔑 API 키")
        youtube_key = st.text_input("YouTube API Key", type="password", value=os.getenv("YOUTUBE_API_KEY", ""))
        anthropic_key = st.text_input("Anthropic API Key", type="password", value=os.getenv("ANTHROPIC_API_KEY", ""))
        
        st.divider()
        
        # 언어/지역
        st.subheader("🌍 언어 / 지역")
        selected_language = st.selectbox("언어", list(REGIONS.keys()))
        countries = REGIONS[selected_language]["countries"]
        selected_country_name = st.selectbox("국가", list(countries.keys()))
        selected_country_code = countries[selected_country_name]
        
        st.divider()
        
        # 기간
        st.subheader("📅 분석 기간")
        selected_period = st.selectbox("기간", list(TIME_PERIODS.keys()))
        days = TIME_PERIODS[selected_period]
        
        st.divider()
        
        # 카테고리
        st.subheader("📂 카테고리")
        selected_category = st.selectbox("카테고리", list(CATEGORIES.keys()))
        category_id = CATEGORIES[selected_category]
        
        st.divider()
        
        # 연결 상태
        st.subheader("📡 연결 상태")
        if youtube_key:
            st.success("✅ YouTube 연결됨")
        else:
            st.warning("⚠️ YouTube 키 필요")
        if anthropic_key:
            st.success("✅ Anthropic 연결됨")
        else:
            st.info("ℹ️ 대본 생성 시 필요")
    
    # ============ 메인 탭 ============
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "🔥 인기 영상", "📈 급상승 키워드", "🔍 키워드 검색", "📊 경쟁 채널", "📝 대본 생성"
    ])
    
    # ============ 탭 1: 인기 영상 ============
    with tab1:
        st.header("🔥 기간별 인기 영상")
        
        col1, col2 = st.columns([3, 1])
        with col1:
            st.info(f"🌍 **{selected_language}** > **{selected_country_name}** | 📂 **{selected_category}** | 📅 **{selected_period}**")
        with col2:
            analyze_btn = st.button("🔍 분석 시작", type="primary", use_container_width=True, key="trending_btn")
        
        if analyze_btn:
            if not youtube_key:
                st.error("YouTube API 키를 입력해주세요.")
            else:
                analyzer = YouTubeAnalyzer(youtube_key)
                
                with st.spinner("인기 영상 분석 중..."):
                    videos = analyzer.get_trending_videos(
                        region_code=selected_country_code,
                        category_id=category_id,
                        max_results=50
                    )
                
                if videos:
                    st.session_state["trending_videos"] = videos
                    st.session_state["trending_region"] = selected_country_name
                    st.success(f"✅ {len(videos)}개 영상 분석 완료!")
                else:
                    st.warning("영상을 가져올 수 없습니다.")
        
        if "trending_videos" in st.session_state:
            videos = st.session_state["trending_videos"]
            
            # 통계 요약
            st.subheader("📊 통계 요약")
            col1, col2, col3, col4, col5 = st.columns(5)
            
            avg_views = sum(v["views"] for v in videos) / len(videos)
            avg_likes = sum(v["like_rate"] for v in videos) / len(videos)
            avg_duration = sum(v["duration_seconds"] for v in videos) / len(videos)
            total_views = sum(v["views"] for v in videos)
            
            col1.metric("분석 영상", f"{len(videos)}개")
            col2.metric("평균 조회수", format_number(int(avg_views)))
            col3.metric("총 조회수", format_number(total_views))
            col4.metric("평균 좋아요율", f"{avg_likes:.2f}%")
            col5.metric("평균 길이", format_duration(int(avg_duration)))
            
            # 인기 키워드
            st.subheader("🏷️ 제목에서 추출한 인기 키워드")
            titles = [v["title"] for v in videos]
            keywords = extract_keywords(titles, top_n=20)
            keyword_html = " ".join([f'<span class="keyword-tag">{kw} ({count})</span>' for kw, count in keywords])
            st.markdown(keyword_html, unsafe_allow_html=True)
            
            # 업로드 패턴
            st.subheader("⏰ 업로드 패턴 분석")
            col1, col2 = st.columns(2)
            
            with col1:
                st.write("**요일별 분포**")
                days_count = Counter([v["upload_day"] for v in videos if v["upload_day"]])
                if days_count:
                    day_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
                    day_df = pd.DataFrame([(d, days_count.get(d, 0)) for d in day_order], columns=["요일", "영상 수"])
                    st.bar_chart(day_df.set_index("요일"))
            
            with col2:
                st.write("**시간대별 분포**")
                hours_count = Counter([v["upload_hour"] for v in videos if v.get("upload_datetime")])
                if hours_count:
                    hour_df = pd.DataFrame([(h, hours_count.get(h, 0)) for h in range(24)], columns=["시간", "영상 수"])
                    st.bar_chart(hour_df.set_index("시간"))
            
            # 제목 패턴 분석
            st.subheader("📝 성공하는 제목 패턴")
            col1, col2, col3, col4, col5 = st.columns(5)
            
            num_with_number = sum(1 for v in videos if v['title_patterns']['has_number'])
            num_with_question = sum(1 for v in videos if v['title_patterns']['has_question'])
            num_with_emoji = sum(1 for v in videos if v['title_patterns']['has_emoji'])
            num_with_emotion = sum(1 for v in videos if v['title_patterns']['has_emotion'])
            avg_title_len = sum(v['title_patterns']['length'] for v in videos) / len(videos)
            
            col1.metric("🔢 숫자 포함", f"{num_with_number/len(videos)*100:.0f}%")
            col2.metric("❓ 질문형", f"{num_with_question/len(videos)*100:.0f}%")
            col3.metric("😀 이모지", f"{num_with_emoji/len(videos)*100:.0f}%")
            col4.metric("💥 감정키워드", f"{num_with_emotion/len(videos)*100:.0f}%")
            col5.metric("📏 평균 제목길이", f"{avg_title_len:.0f}자")
            
            # 영상 목록
            st.subheader("🎬 인기 영상 TOP 20")
            
            for i, video in enumerate(videos[:20], 1):
                with st.expander(f"{i}위. {video['title'][:55]}... ({format_number(video['views'])}회)"):
                    col1, col2 = st.columns([1, 2])
                    
                    with col1:
                        if video.get("thumbnail"):
                            st.image(video["thumbnail"], use_container_width=True)
                        st.markdown(f"[▶️ 영상 보기](https://youtube.com/watch?v={video['video_id']})")
                    
                    with col2:
                        st.write(f"**채널:** {video['channel_title']}")
                        st.write(f"**조회수:** {video['views']:,}회")
                        
                        col_a, col_b, col_c = st.columns(3)
                        col_a.write(f"**좋아요:** {video['likes']:,}")
                        col_b.write(f"**좋아요율:** {video['like_rate']:.2f}%")
                        col_c.write(f"**댓글:** {video['comments']:,}")
                        
                        st.write(f"**영상 길이:** {video['duration_formatted']}")
                        st.write(f"**업로드:** {video['published_at'][:10] if video['published_at'] else 'N/A'}")
                        
                        patterns = video['title_patterns']
                        tags = []
                        if patterns['has_number']: tags.append("🔢숫자")
                        if patterns['has_question']: tags.append("❓질문형")
                        if patterns['has_emoji']: tags.append("😀이모지")
                        if patterns['has_emotion']: tags.append("💥감정")
                        if tags:
                            st.write(f"**제목 패턴:** {' '.join(tags)}")
    
    # ============ 탭 2: 급상승 키워드 ============
    with tab2:
        st.header("📈 급상승 키워드")
        
        col1, col2 = st.columns([3, 1])
        with col1:
            st.info(f"🌍 **{selected_country_name}** 실시간 인기 검색어 (Google Trends + YouTube)")
        with col2:
            trends_btn = st.button("🔍 키워드 분석", type="primary", use_container_width=True, key="trends_btn")
        
        if trends_btn:
            trends = TrendsAnalyzer()
            
            with st.spinner("급상승 키워드 분석 중..."):
                trending_searches = trends.get_trending_searches(selected_country_code)
                st.session_state["trending_searches"] = trending_searches
                
                # 카테고리별 기본 키워드
                cat_keywords = {
                    "전체": ["뉴스", "이슈", "트렌드"],
                    "엔터테인먼트": ["드라마", "예능", "연예인"],
                    "음악": ["노래", "음악", "뮤비"],
                    "게임": ["게임", "롤", "스팀"],
                    "교육": ["공부", "강의", "영어"],
                    "과학/기술": ["AI", "기술", "과학"]
                }
                base_kw = cat_keywords.get(selected_category, ["트렌드"])
                
                related = trends.get_related_queries(base_kw, geo=selected_country_code, timeframe=TRENDS_TIMEFRAMES[selected_period])
                st.session_state["related_queries"] = related
            
            st.success("✅ 키워드 분석 완료!")
        
        if "trending_searches" in st.session_state:
            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader("🔥 실시간 급상승 검색어")
                searches = st.session_state["trending_searches"]
                if searches:
                    for i, keyword in enumerate(searches[:15], 1):
                        col_a, col_b = st.columns([3, 1])
                        with col_a:
                            st.write(f"**{i}. {keyword}**")
                        with col_b:
                            if st.button("🔍", key=f"search_trend_{i}"):
                                st.session_state["quick_search"] = keyword
                else:
                    st.info("데이터를 가져올 수 없습니다. 나중에 다시 시도해주세요.")
            
            with col2:
                st.subheader("📈 연관 키워드")
                related = st.session_state.get("related_queries", {})
                
                if related.get("rising"):
                    st.write("**🚀 급상승:**")
                    for kw in related["rising"][:8]:
                        st.write(f"• {kw}")
                
                if related.get("top"):
                    st.write("**⭐ 인기:**")
                    for kw in related["top"][:8]:
                        st.write(f"• {kw}")
        
        # 키워드로 YouTube 검색
        st.divider()
        st.subheader("🎬 키워드별 인기 영상 찾기")
        
        quick_search = st.session_state.get("quick_search", "")
        keyword_input = st.text_input("검색할 키워드", value=quick_search, placeholder="예: AI, 다이어트, 주식")
        
        if keyword_input and youtube_key:
            if st.button("🎬 인기 영상 검색", key="kw_video_search"):
                analyzer = YouTubeAnalyzer(youtube_key)
                published_after = datetime.now() - timedelta(days=days)
                
                with st.spinner(f"'{keyword_input}' 검색 중..."):
                    videos = analyzer.search_videos(
                        query=keyword_input,
                        region_code=selected_country_code,
                        language=REGIONS[selected_language]["language"],
                        published_after=published_after,
                        max_results=20
                    )
                
                if videos:
                    st.success(f"✅ {len(videos)}개 영상!")
                    
                    for i, video in enumerate(videos[:10], 1):
                        with st.expander(f"{i}. {video['title'][:45]}... ({format_number(video['views'])}회)"):
                            col1, col2 = st.columns([1, 2])
                            with col1:
                                if video.get("thumbnail"):
                                    st.image(video["thumbnail"], use_container_width=True)
                            with col2:
                                st.write(f"**채널:** {video['channel_title']}")
                                st.write(f"**조회수:** {video['views']:,}")
                                st.write(f"**좋아요율:** {video['like_rate']:.2f}%")
                                st.write(f"**길이:** {video['duration_formatted']}")
                                st.markdown(f"[▶️ 영상 보기](https://youtube.com/watch?v={video['video_id']})")
    
    # ============ 탭 3: 키워드 검색 ============
    with tab3:
        st.header("🔍 키워드 심층 검색")
        
        col1, col2, col3 = st.columns([2, 1, 1])
        with col1:
            search_keyword = st.text_input("검색 키워드", placeholder="예: 파이썬 강의", key="deep_kw")
        with col2:
            search_order = st.selectbox("정렬", ["조회수 순", "최신순", "관련성 순"])
        with col3:
            max_search = st.selectbox("결과 수", [10, 20, 30, 50])
        
        order_map = {"조회수 순": "viewCount", "최신순": "date", "관련성 순": "relevance"}
        
        if search_keyword and youtube_key:
            if st.button("🔍 검색", type="primary", key="deep_search_btn"):
                analyzer = YouTubeAnalyzer(youtube_key)
                published_after = datetime.now() - timedelta(days=days)
                
                with st.spinner("검색 중..."):
                    videos = analyzer.search_videos(
                        query=search_keyword,
                        region_code=selected_country_code,
                        language=REGIONS[selected_language]["language"],
                        published_after=published_after,
                        max_results=max_search,
                        order=order_map[search_order]
                    )
                
                if videos:
                    st.session_state["search_results"] = videos
                    st.success(f"✅ {len(videos)}개 영상!")
        
        if "search_results" in st.session_state:
            videos = st.session_state["search_results"]
            
            # 통계
            st.subheader("📊 검색 결과 분석")
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("검색 결과", f"{len(videos)}개")
            col2.metric("평균 조회수", format_number(int(sum(v['views'] for v in videos) / len(videos))))
            col3.metric("평균 좋아요율", f"{sum(v['like_rate'] for v in videos) / len(videos):.2f}%")
            col4.metric("평균 길이", format_duration(int(sum(v['duration_seconds'] for v in videos) / len(videos))))
            
            # 테이블
            df = pd.DataFrame([{
                "순위": i,
                "제목": v["title"][:35] + "...",
                "채널": v["channel_title"][:15],
                "조회수": format_number(v["views"]),
                "좋아요율": f"{v['like_rate']:.1f}%",
                "길이": v["duration_formatted"]
            } for i, v in enumerate(videos, 1)])
            
            st.dataframe(df, use_container_width=True, hide_index=True)
            
            # 상세
            for i, video in enumerate(videos[:10], 1):
                with st.expander(f"상세: {video['title'][:40]}..."):
                    col1, col2 = st.columns([1, 2])
                    with col1:
                        if video.get("thumbnail"):
                            st.image(video["thumbnail"], use_container_width=True)
                    with col2:
                        st.write(f"**채널:** {video['channel_title']}")
                        st.write(f"**조회수:** {video['views']:,}")
                        st.write(f"**좋아요:** {video['likes']:,} ({video['like_rate']:.2f}%)")
                        st.write(f"**댓글:** {video['comments']:,}")
                        st.write(f"**길이:** {video['duration_formatted']}")
                        st.markdown(f"[▶️ 영상 보기](https://youtube.com/watch?v={video['video_id']})")
    
    # ============ 탭 4: 경쟁 채널 ============
    with tab4:
        st.header("📊 경쟁 채널 분석")
        
        channel_url = st.text_input("채널 URL", placeholder="https://www.youtube.com/@channelname")
        
        if channel_url and youtube_key:
            if st.button("📊 채널 분석", type="primary", key="ch_analyze"):
                analyzer = YouTubeAnalyzer(youtube_key)
                
                with st.spinner("채널 분석 중..."):
                    channel_id = analyzer.get_channel_id_from_url(channel_url)
                    
                    if channel_id:
                        info = analyzer.get_channel_info(channel_id)
                        videos = analyzer.get_channel_videos(channel_id, max_results=30)
                        
                        st.session_state["ch_info"] = info
                        st.session_state["ch_videos"] = videos
                        st.success("✅ 분석 완료!")
                    else:
                        st.error("채널을 찾을 수 없습니다.")
        
        if "ch_info" in st.session_state:
            info = st.session_state["ch_info"]
            videos = st.session_state.get("ch_videos", [])
            
            # 채널 정보
            st.subheader(f"📺 {info['title']}")
            
            col1, col2 = st.columns([1, 3])
            with col1:
                if info.get("thumbnail"):
                    st.image(info["thumbnail"], width=150)
            with col2:
                c1, c2, c3 = st.columns(3)
                c1.metric("구독자", format_number(info['subscribers']))
                c2.metric("총 조회수", format_number(info['total_views']))
                c3.metric("영상 수", format_number(info['video_count']))
            
            if videos:
                st.divider()
                
                # 성과 분석
                st.subheader("📈 최근 영상 성과")
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("평균 조회수", format_number(int(sum(v['views'] for v in videos) / len(videos))))
                c2.metric("평균 좋아요율", f"{sum(v['like_rate'] for v in videos) / len(videos):.2f}%")
                c3.metric("평균 댓글", format_number(int(sum(v['comments'] for v in videos) / len(videos))))
                c4.metric("평균 길이", format_duration(int(sum(v['duration_seconds'] for v in videos) / len(videos))))
                
                # 키워드
                st.subheader("🏷️ 채널 인기 키워드")
                keywords = extract_keywords([v["title"] for v in videos], top_n=15)
                keyword_html = " ".join([f'<span class="keyword-tag">{kw} ({cnt})</span>' for kw, cnt in keywords])
                st.markdown(keyword_html, unsafe_allow_html=True)
                
                # 영상 목록
                st.subheader("🎬 최근 영상")
                for i, video in enumerate(videos[:10], 1):
                    with st.expander(f"{i}. {video['title'][:45]}... ({format_number(video['views'])}회)"):
                        col1, col2 = st.columns([1, 2])
                        with col1:
                            if video.get("thumbnail"):
                                st.image(video["thumbnail"], use_container_width=True)
                        with col2:
                            st.write(f"**조회수:** {video['views']:,}")
                            st.write(f"**좋아요율:** {video['like_rate']:.2f}%")
                            st.write(f"**댓글:** {video['comments']:,}")
                            st.write(f"**길이:** {video['duration_formatted']}")
                            st.markdown(f"[▶️ 보기](https://youtube.com/watch?v={video['video_id']})")
    
    # ============ 탭 5: 대본 생성 ============
    with tab5:
        st.header("📝 대본 생성")
        
        if not anthropic_key:
            st.warning("👈 사이드바에서 Anthropic API 키를 입력해주세요.")
            st.info("**발급:** https://console.anthropic.com → API Keys → Create Key")
        else:
            st.success("✅ Anthropic 연결됨")
            
            topic = st.text_input("영상 주제", placeholder="예: 2024년 AI 트렌드")
            
            c1, c2 = st.columns(2)
            with c1:
                style = st.selectbox("스타일", ["정보 전달형", "스토리텔링형", "튜토리얼형", "리뷰형"])
            with c2:
                length = st.selectbox("영상 길이", ["숏폼 (1분)", "미드폼 (5분)", "롱폼 (10분)", "롱폼 (15분+)"])
            
            if st.button("✨ 대본 생성", type="primary") and topic:
                st.info("🚧 대본 생성 기능 준비 중...")


if __name__ == "__main__":
    main()
