import os
import re
import sys
from datetime import datetime
import httpx
from fastmcp import FastMCP
from youtube_transcript_api import YouTubeTranscriptApi

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
YOUTUBE_API_URL = 'https://www.googleapis.com/youtube/v3'

# MCP 서버 생성
mcp = FastMCP("youtube_data_collector")

def extract_video_id(url: str) -> str:
    """유튜브 Shorts를 포함한 다양한 URL 형태에서 비디오 ID 11자리를 추출합니다."""
    patterns = [
        r"(?:v=|\/shorts\/|\/embed\/|\/v\/|youtu\.be\/)([0-9A-Za-z_-]{11})",
        r"(?:v=|\/)([0-9A-Za-z_-]{11})"
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return ""

# Tool 1 : 유튜브 영상 URL 자막 추출
@mcp.tool()
def get_youtube_transcript(url: str, languages: list[str] = ["ko", "en"]) -> str:
    """
    유튜브 영상 URL에서 비디오 ID를 추출하고 해당 영상의 자막을 가져옵니다.
    """
    video_id = extract_video_id(url)
    if not video_id:
        return "에러: 유효한 유튜브 URL이 아닙니다."

    try:
        ytt_api = YouTubeTranscriptApi()
        # 내부 블로킹 API를 호출할 때는 예외 처리를 명확히 합니다.
        fetched_transcript = ytt_api.fetch(video_id, languages=languages)
        transcript_text = " ".join([snippet.text for snippet in fetched_transcript])
        return transcript_text
        
    except Exception as e:
        print(f"Transcript Error: {e}", file=sys.stderr)
        return f"자막을 가져오는 중 오류가 발생했습니다: {str(e)}"
    

# Tool 2 : 유튜브 영상 검색 및 세부 정보 추출
@mcp.tool()
async def search_youtube_videos(query: str, order: str = "relevance", max_results: int = 5) -> list:
    """
    유튜브에서 특정 키워드로 동영상을 검색하고 세부 정보를 가져옵니다.
    """
    if not YOUTUBE_API_KEY:
        print("Error: YOUTUBE_API_KEY가 설정되지 않았습니다.", file=sys.stderr)
        return []

    valid_orders = ["date", "rating", "relevance", "title", "videoCount", "viewCount"]
    if order not in valid_orders:
        raise ValueError(f"order 값은 {valid_orders} 중 하나여야 합니다.")

    # httpx.AsyncClient를 이용한 비동기 타임아웃 안전망 처리 (10초 타임아웃)
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            # 1️⃣ 유튜브 검색 요청
            search_url = f"{YOUTUBE_API_URL}/search"
            search_params = {
                "part": "snippet",
                "q": query,
                "type": "video",
                "order": order,
                "maxResults": max_results,
                "key": YOUTUBE_API_KEY
            }
            
            search_response = await client.get(search_url, params=search_params)
            search_response.raise_for_status()
            search_data = search_response.json()
            
            video_ids = [item["id"]["videoId"] for item in search_data.get("items", [])]
            if not video_ids:
                return []

            # 2️⃣ 상세 정보 조회
            video_details_url = f"{YOUTUBE_API_URL}/videos"
            details_params = {
                "part": "snippet,statistics",
                "id": ",".join(video_ids),
                "key": YOUTUBE_API_KEY
            }
            
            details_response = await client.get(video_details_url, params=details_params)
            details_response.raise_for_status()
            details_data = details_response.json()

            # 3️⃣ 결과 정리
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
            print(f"Search Error: {e}", file=sys.stderr)
            return []
    

# Tool 3 : YouTube 동영상 URL로부터 채널 정보와 최근 5개 동영상 조회
@mcp.tool()
async def get_channel_info(video_url: str, order: str = "date", max_results: int = 5) -> dict:
    """
    YouTube 동영상 URL로부터 채널 정보와 영상 목록을 가져옵니다.
    """
    video_id = extract_video_id(video_url)
    if not video_id or not YOUTUBE_API_KEY:
        return {}

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            # 1️⃣ 비디오 정보 가져오기
            video_url_api = f"{YOUTUBE_API_URL}/videos"
            video_res = await client.get(video_url_api, params={"part": "snippet", "id": video_id, "key": YOUTUBE_API_KEY})
            video_data = video_res.json()
            
            if not video_data.get("items"):
                return {}

            channel_id = video_data["items"][0]["snippet"]["channelId"]

            # 2️⃣ 채널 정보 가져오기
            channel_url_api = f"{YOUTUBE_API_URL}/channels"
            channel_res = await client.get(channel_url_api, params={"part": "snippet,statistics", "id": channel_id, "key": YOUTUBE_API_KEY})
            channel_items = channel_res.json().get("items", [])
            if not channel_items:
                return {}
            channel_data = channel_items[0]

            # 3️⃣ 채널의 영상 목록 가져오기
            search_url_api = f"{YOUTUBE_API_URL}/search"
            search_params = {
                "part": "snippet",
                "channelId": channel_id,
                "maxResults": max_results,
                "order": order,
                "type": "video",
                "key": YOUTUBE_API_KEY
            }
            search_res = await client.get(search_url_api, params=search_params)
            search_data = search_res.json()
            
            videos = []
            for item in search_data.get("items", []):
                snippet = item["snippet"]
                videos.append({
                    "title": snippet["title"],
                    "url": f"https://www.youtube.com/watch?v={item['id']['videoId']}",
                    "published": snippet["publishedAt"],
                    "thumbnail": snippet["thumbnails"].get("high", {}).get("url", "")
                })

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
            print(f"Channel Info Error: {e}", file=sys.stderr)
            return {}


# Tool 4 : YouTube 동영상 URL로부터 댓글 수집
@mcp.tool()
async def get_youtube_comments(video_url: str, order: str = "relevance", max_results: int = 10) -> list:
    """
    유튜브 영상 댓글을 수집합니다.
    """
    video_id = extract_video_id(video_url)
    if not video_id or not YOUTUBE_API_KEY:
        return []

    if order not in ["relevance", "time"]:
        raise ValueError("order는 'relevance' 또는 'time' 중 하나여야 합니다.")

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            comment_url = f"{YOUTUBE_API_URL}/commentThreads"
            params = {
                "part": "snippet",
                "videoId": video_id,
                "order": order,
                "maxResults": max_results,
                "key": YOUTUBE_API_KEY
            }
            response = await client.get(comment_url, params=params)
            response.raise_for_status()
            data = response.json()

            comments = []
            for item in data.get("items", []):
                snippet = item["snippet"]["topLevelComment"]["snippet"]
                comments.append({
                    "author": snippet["authorDisplayName"],
                    "text": snippet["textOriginal"],
                    "likeCount": snippet.get("likeCount", 0),
                    "publishedAt": snippet["publishedAt"]
                })

            return comments
        except Exception as e:
            print(f"Comments Error: {e}", file=sys.stderr)
            return []