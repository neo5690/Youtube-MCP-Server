# 2mcp/data_collector_mcp.py와 내용 동일, 코드 일부 수정
# FastMCP Cloud에서 배포, YouTube API Key 환경변수 설정 필요

from fastmcp import FastMCP
from youtube_transcript_api import YouTubeTranscriptApi
import re
import requests
import os
from datetime import datetime


YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
YOUTUBE_API_URL = 'https://www.googleapis.com/youtube/v3'


# MCP 서버 생성
mcp = FastMCP("youtube_data_collector")

# Tool 1 : 유튜브 영상 URL 자막 추출
@mcp.tool()
def get_youtube_transcript(url: str, languages: list[str] = ["ko", "en"]) -> str:
    """
    유튜브 영상 URL에서 비디오 ID를 추출하고 해당 영상의 자막을 가져옵니다.

    Args:
        url (str): 유튜브 영상의 전체 URL.
        languages (list[str]): 시도할 자막 언어 코드 목록 (내림차순 우선순위). 기본값은 ["ko", "en"].

    Returns:
        str: 추출된 자막 텍스트 전체. 실패 시 빈 문자열을 반환합니다.
    """

    # 1️⃣ URL에서 비디오 ID 추출
    video_id_match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11}).*", url)
    if not video_id_match:
        return ""
    video_id = video_id_match.group(1)

    try:
        # 2️⃣ YouTubeTranscriptApi 인스턴스 생성 및 fetch() 메서드 호출
        ytt_api = YouTubeTranscriptApi()
        
        # fetch()를 호출하여 FetchedTranscript 객체를 반환받습니다.
        fetched_transcript = ytt_api.fetch(
            video_id, 
            languages=languages
        )

        # 2️⃣ 객체 속성으로 접근
        transcript_text = " ".join([snippet.text for snippet in fetched_transcript])
        return transcript_text
        
    except Exception as e:
        print(f"Error: {e}")
        return ""
    

# Tool 2 : 유튜브 영상 검색 및 세부 정보 추출
@mcp.tool()
def search_youtube_videos(query: str, order: str = "relevance", max_results: int = 5) -> list:
    """
    유튜브에서 특정 키워드로 동영상을 검색하고 세부 정보를 가져옵니다.

    Parameters
    ----------
    query : str
        검색할 키워드
    order : str, optional
        정렬 기준 (기본값: 'relevance')
        - relevance : 관련성 높은 순
        - date : 최신순
        - viewCount : 조회수 많은 순
        - rating : 평점순
        - title : 제목 알파벳순
        - videoCount : 채널 영상 수 많은 순
    max_results : int, optional
        검색 결과 개수 (기본값: 5)
    """

    try:
        # 1️⃣ order 값 검증
        valid_orders = ["date", "rating", "relevance", "title", "videoCount", "viewCount"]
        if order not in valid_orders:
            raise ValueError(f"order 값은 {valid_orders} 중 하나여야 합니다.")

        # 2️⃣ 유튜브 검색 요청
        search_url = (
            f"{YOUTUBE_API_URL}/search?"
            f"part=snippet&q={requests.utils.quote(query)}&type=video"
            f"&order={order}&maxResults={max_results}&key={YOUTUBE_API_KEY}"
        )
        search_response = requests.get(search_url)
        search_data = search_response.json()
        video_ids = [item["id"]["videoId"] for item in search_data.get("items", [])]

        if not video_ids:
            return []

        # 3️⃣ 상세 정보 조회
        video_details_url = (
            f"{YOUTUBE_API_URL}/videos?"
            f"part=snippet,statistics&id={','.join(video_ids)}&key={YOUTUBE_API_KEY}"
        )
        details_response = requests.get(video_details_url)
        details_response.raise_for_status()
        details_data = details_response.json()

        # 4️⃣ 결과 정리
        videos = []
        for item in details_data.get("items", []):
            snippet = item.get("snippet", {})
            statistics = item.get("statistics", {})
            thumbnails = snippet.get("thumbnails", {})
            high_thumbnail = thumbnails.get("high", {})

            video_card = {
                "title": snippet.get("title", "N/A"),
                "publishedDate": snippet.get("publishedAt", ""),
                "channelName": snippet.get("channelTitle", "N/A"),
                "channelId": snippet.get("channelId", ""),
                "thumbnailUrl": high_thumbnail.get("url", ""),
                "viewCount": int(statistics.get("viewCount", 0)),
                "likeCount": int(statistics.get("likeCount", 0)) if "likeCount" in statistics else None,
                "url": f"https://www.youtube.com/watch?v={item.get('id', '')}",
            }
            videos.append(video_card)

        return videos

    except Exception as e:
        print(f"Error: {e}")
        return []
    

# Tool 3 : YouTube 동영상 URL로부터 채널 정보와 최근 5개 동영상 조회
@mcp.tool()
def get_channel_info(video_url: str, order: str = "date", max_results: int = 5) -> dict:
    """
    YouTube 동영상 URL로부터 채널 정보와 영상 목록을 가져옵니다.

    Parameters
    ----------
    video_url : str
        유튜브 영상 URL
    order : str, optional
        영상 정렬 기준 (기본값: 'date')
        - 'date': 최신순
        - 'viewCount': 조회수순
        - 'rating': 평점순
    max_results : int, optional
        가져올 영상 개수 (기본값: 5)
    """

    # 1️⃣ URL에서 비디오 ID 추출
    video_id_match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11})", video_url)
    if not video_id_match:
        return {}

    video_id = video_id_match.group(1)

    try:
        # 2️⃣ 비디오 정보 가져오기 (채널 ID 추출)
        video_api = f"{YOUTUBE_API_URL}/videos?part=snippet,statistics&id={video_id}&key={YOUTUBE_API_KEY}"
        video_data = requests.get(video_api).json()
        if not video_data.get("items"):
            # 비디오가 없으면 빈 딕셔너리 반환
            return {}

        video_info = video_data["items"][0]
        channel_id = video_info["snippet"]["channelId"]

        # 3️⃣ 채널 정보 가져오기
        channel_api = f"{YOUTUBE_API_URL}/channels?part=snippet,statistics&id={channel_id}&key={YOUTUBE_API_KEY}"
        channel_data = requests.get(channel_api).json()["items"][0]

        # 4️⃣ 채널의 영상 목록 가져오기 (order, max_results 반영)
        search_url = (
            f"{YOUTUBE_API_URL}/search?"
            f"part=snippet&channelId={channel_id}&maxResults={max_results}"
            f"&order={order}&type=video&key={YOUTUBE_API_KEY}"
        )
        search_data = requests.get(search_url).json()
        videos = []
        for item in search_data.get("items", []):
            snippet = item["snippet"]
            videos.append({
                "title": snippet["title"],
                "url": f"https://www.youtube.com/watch?v={item['id']['videoId']}",
                "published": snippet["publishedAt"],
                "thumbnail": snippet["thumbnails"]["high"]["url"]
            })

        # 5️⃣ 최종 결과 반환
        return {
            "channelTitle": channel_data["snippet"]["title"],
            "channelUrl": f"https://www.youtube.com/channel/{channel_id}",
            "subscriberCount": channel_data["statistics"].get("subscriberCount", "0"),
            "viewCount": channel_data["statistics"].get("viewCount", "0"),
            "videoCount": channel_data["statistics"].get("videoCount", "0"),
            "videos": videos,
            "retrievedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
    except Exception as e:
        print(f"Error during channel info fetch: {e}")
        return {}


# Tool 4 : YouTube 동영상 URL로부터 댓글 수집
@mcp.tool()
def get_youtube_comments(video_url: str, order: str = "relevance", max_results: int = 10) -> list:
    """
    유튜브 영상 댓글을 수집합니다.

    Parameters
    ----------
    video_url : str
        유튜브 영상 URL
    order : str, optional
        댓글 정렬 기준 (기본값: 'relevance')
        - 'relevance': 관련성 높은 댓글 우선
        - 'time': 최신 댓글 우선
    max_results : int, optional
        가져올 댓글 수 (기본값: 10)
    """

    # 1️⃣ 비디오 ID 추출
    video_id_match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11}).*", video_url)
    if not video_id_match:
        return []
    video_id = video_id_match.group(1)

    # 2️⃣ order 파라미터 유효성 검사
    if order not in ["relevance", "time"]:
        raise ValueError("order는 'relevance' 또는 'time' 중 하나여야 합니다.")

    # 3️⃣ API 요청 URL 구성
    comment_url = (
        f"{YOUTUBE_API_URL}/commentThreads?"
        f"part=snippet&videoId={video_id}&order={order}&maxResults={max_results}&key={YOUTUBE_API_KEY}"
    )

    try:
        response = requests.get(comment_url)
        response.raise_for_status()
        data = response.json()

        if "items" not in data:
            return []

        # 4️⃣ 결과 파싱
        comments = []
        for item in data["items"]:
            snippet = item["snippet"]["topLevelComment"]["snippet"]
            comments.append({
                "author": snippet["authorDisplayName"],
                "text": snippet["textOriginal"],
                "likeCount": snippet.get("likeCount", 0),
                "publishedAt": snippet["publishedAt"]
            })

        return comments
    except Exception as e:
        print(f"Error during comment fetch: {e}")
        return []