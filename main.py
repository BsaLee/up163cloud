import asyncio
from functools import partial
import os
import json
from typing import Union
import aiohttp
import requests
import time

from login import login
from get_cloud_info import get_cloud_info


class NcmUploader:

    def __init__(self, cookie: str):
        self._cookie = cookie
        self._show_cloud_music_detail()

    def _show_cloud_music_detail(self):
        if not get_cloud_info(self._cookie):
            raise ValueError("检查 cookie 有效性")

    async def upload(self, music_json_path: str, concurrency: int = 10):
        songs_data = self._read_songs_data(music_json_path)
        song_info_list = self.get_all_song_info(songs_data)
        song_info_list = self.get_resume_song_info_list(song_info_list)
        await self._async_upload_songs(song_info_list, concurrency)

    async def _async_upload_songs(self, song_info_list: list, concurrency: int):
        sem = asyncio.Semaphore(concurrency)  # 创建信号量
        async def _upload_with_semaphore(song_info):
            async with sem:  # 使用信号量控制并发
                return await self._upload_one_song(song_info)
        
        tasks = []
        for song_info in song_info_list:
            tasks.append(_upload_with_semaphore(song_info))  # 直接创建协程任务
        await asyncio.gather(*tasks)

    async def _upload_one_song(self, song_info: dict):
        try:
            await self._try_to_upload_one_song(song_info)
        except Exception as e:
            print(f"上传过程异常，跳过该歌曲：{e}")
            self._save_failed_id(song_info["id"])

    async def _try_to_upload_one_song(self, song_info: dict):
        song_id = int(song_info["id"])
        print(f"正在导入歌曲ID: {song_id}")

        # 已上传则跳过
        if await self._has_uploaded(song_id):
            print("该歌曲已上传，跳过！")
            return

        # 查询歌曲的详细信息
        song_details = self.get_song_details([song_id])
        if song_details:
            song_name = song_details[0]["name"]
            song_artist = song_details[0]["ar"][0]["name"]
            song_album = song_details[0]["al"]["name"]
            print(f"歌曲名: {song_name}, 演唱者: {song_artist}, 专辑: {song_album}")
            # 更新 song_info 添加 artist 和 album 信息
            song_info["artist"] = song_artist
            song_info["album"] = song_album
            await self._send_upload_request(song_info)

    # 获取当前时间戳（秒）
    @staticmethod
    def get_current_timestamp():
        return int(time.time())

    # 读取 cookies.txt 文件
    @staticmethod
    def read_cookie():
        if os.path.exists("cookies.txt"):
            with open("cookies.txt", "r") as f:
                cookie = f.read().strip()
                if cookie:
                    return cookie
        return None

    # 读取歌曲.json 文件并返回数据
    @staticmethod
    def _read_songs_data(music_json_path: str) -> list:
        with open(music_json_path, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
                return data.get("data", [])
            except json.JSONDecodeError:
                print("歌曲.json 格式错误")
                return []

    # 提取所有歌曲的 id 和其他信息
    @staticmethod
    def get_all_song_info(songs_data):
        song_info_list = []
        for song in songs_data:
            song_info = {
                "id": song.get("id"),
                "size": song.get("size"),
                "ext": song.get("ext"),
                "bitrate": song.get("bitrate"),
                "md5": song.get("md5"),
            }
            song_info_list.append(song_info)
        return song_info_list

    # 查询歌曲详情
    @staticmethod
    def get_song_details(song_ids: list):
        ids = ",".join(map(str, song_ids))  # 将多个 id 拼接成一个以逗号分隔的字符串
        timestamp = NcmUploader.get_current_timestamp()  # 获取当前时间戳
        url = f"http://localhost:3000/song/detail?ids={ids}&time={timestamp}"
        print(f"查询歌曲详情 URL: {url}")
        response = requests.get(url)
        try:
            response_data = response.json()
            if response_data.get("code") == 200:
                return response_data.get("songs", [])
            else:
                print("获取歌曲详情失败:", response_data.get("message"))
                return []
        except json.JSONDecodeError:
            print("响应内容无法解析为JSON:", response.text)
            return []

    # 判断歌曲是否已上传云盘
    async def _has_uploaded(self, song_id: int) -> bool:
        url = (
            f"http://localhost:3000/user/cloud/detail?id={song_id}&cookie={self._cookie}"
        )
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                try:
                    response_data = await response.json()
                    if response_data.get("code") == 200 and len(response_data["data"]) != 0:
                        return True
                    else:
                        print("获取云盘歌曲详情失败:", response_data.get("message"))
                        return False
                except json.JSONDecodeError:
                    print("获取云盘歌曲信息失败，响应内容无法解析为JSON:", response.text)
                    return False

    async def _send_upload_request(self, song_info: dict):
        song_id = song_info["id"]
        artist = song_info["artist"]
        album = song_info["album"]
        file_size = song_info["size"]
        bitrate = song_info["bitrate"]
        md5 = song_info["md5"]
        file_type = song_info["ext"]

        # 构造完整的请求URL和参数
        timestamp = NcmUploader.get_current_timestamp()  # 获取当前时间戳
        url = f"http://localhost:3000/cloud/import?id={song_id}&cookie={self._cookie}&artist={artist}&album={album}&fileSize={file_size}&bitrate={bitrate}&md5={md5}&fileType={file_type}&time={timestamp}"
        # print(f"执行导入请求 URL: {url}")
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                response_data = await response.json()

        success_songs = response_data.get("data", {}).get("successSongs", [])
        failed = response_data.get("data", {}).get("failed", [])

        if success_songs:
            print(f"歌曲 {song_id} 导入成功！")
        else:
            print(f"歌曲 {song_id} 导入失败，失败原因：{failed}")
            if all(f["code"] == -100 for f in failed):  # 文件已存在的错误码
                print(f"歌曲 {song_id} 文件已存在，跳过")
                self._save_failed_id(song_id)  # 保存失败的 ID

    # 保存失败的 id 到文件
    @staticmethod
    def _save_failed_id(song_id):
        with open("failed_ids.txt", "a") as f:
            f.write(f"{song_id}\n")

    # 获取最后一个上传的异常 id
    @staticmethod
    def _get_last_failed_id() -> Union[int, None]:
        if not os.path.exists("failed_ids.txt"):
            return None
        with open("failed_ids.txt", "r") as f:
            ids = [line.strip() for line in f]
        return int(ids[-1])

    @staticmethod
    def get_resume_song_info_list(song_info_list) -> list:
        last_failed_id = NcmUploader._get_last_failed_id()
        if last_failed_id is None:
            print("暂无上传失败记录，从头开始上传")
            return song_info_list
        for index, song_info in enumerate(song_info_list):
            if int(song_info["id"]) == last_failed_id:
                print(f"当前已上传: {index + 1}，最后上传失败的 id: {song_info['id']}")
                return song_info_list[index + 1 :]
        print("暂未匹配到最后一次失败的 song_id, 将从头开始上传")
        return song_info_list


if __name__ == "__main__":
    if not os.path.exists("cookies.txt"):
        print('未发现 cookies.txt 文件')
        exit(0)
    with open("cookies.txt", "r") as f:
        cookie = f.read().strip()
    ncmUploader = NcmUploader(cookie)
    asyncio.run(ncmUploader.upload('歌曲.json', 10))
