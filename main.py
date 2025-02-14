import os
import json
from typing import Union
import requests
import time

# 导入 login 函数
from login import login  # 直接从 login.py 导入 login 函数
from get_cloud_info import get_cloud_info  # 从 get_cloud_info.py 导入 get_cloud_info 函数

# 获取当前时间戳（秒）
def get_current_timestamp():
    return int(time.time())

# 读取 cookies.txt 文件
def read_cookie():
    if os.path.exists("cookies.txt"):
        with open("cookies.txt", "r") as f:
            cookie = f.read().strip()
            if cookie:
                return cookie
    return None

# 读取歌曲.json 文件并返回数据
def read_songs_data():
    if os.path.exists("歌曲.json"):
        with open("歌曲.json", "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
                return data.get('data', [])
            except json.JSONDecodeError:
                print("歌曲.json 格式错误")
                return []
    else:
        print("歌曲.json 文件不存在")
        return []

# 提取所有歌曲的 id 和其他信息
def get_all_song_info(songs_data):
    song_info_list = []
    for song in songs_data:
        song_info = {
            'id': song.get("id"),
            'size': song.get("size"),
            'ext': song.get("ext"),
            'bitrate': song.get("bitrate"),
            'md5': song.get("md5")
        }
        song_info_list.append(song_info)
    return song_info_list

# 查询歌曲详情
def get_song_details(song_ids):
    ids = ",".join(map(str, song_ids))  # 将多个 id 拼接成一个以逗号分隔的字符串
    timestamp = get_current_timestamp()  # 获取当前时间戳
    url = f"http://localhost:3000/song/detail?ids={ids}&time={timestamp}"
    print(f"查询歌曲详情 URL: {url}")
    response = requests.get(url)
    try:
        response_data = response.json()
        if response_data.get('code') == 200:
            return response_data.get('songs', [])
        else:
            print("获取歌曲详情失败:", response_data.get("message"))
            return []
    except json.JSONDecodeError:
        print("响应内容无法解析为JSON:", response.text)
        return []

# 判断歌曲是否已上传云盘
def has_uploaded(song_id, cookie):
    url = f"http://localhost:3000/user/cloud/detail?id={song_id}&cookie={cookie}"
    response = requests.get(url)
    try:
        response_data = response.json()
        if response_data.get('code') == 200 and len(response_data['data']) != 0:
            return True
        else:
            print("获取云盘歌曲详情失败:", response_data.get("message"))
            return False
    except json.JSONDecodeError:
        print("获取云盘歌曲信息失败，响应内容无法解析为JSON:", response.text)
        return False

# 执行 import 请求
def import_song(song_info, cookie):
    song_id = song_info['id']
    artist = song_info['artist']
    album = song_info['album']
    file_size = song_info['size']
    bitrate = song_info['bitrate']
    md5 = song_info['md5']
    file_type = song_info['ext']
    
    # 构造完整的请求URL和参数
    timestamp = get_current_timestamp()  # 获取当前时间戳
    url = f"http://localhost:3000/cloud/import?id={song_id}&cookie={cookie}&artist={artist}&album={album}&fileSize={file_size}&bitrate={bitrate}&md5={md5}&fileType={file_type}&time={timestamp}"
    #print(f"执行导入请求 URL: {url}")
    
    response = requests.get(url)
    try:
        response_data = response.json()
        return response_data
    except json.JSONDecodeError:
        print("响应内容无法解析为JSON:", response.text)
        return None

# 保存失败的 id 到文件
def save_failed_id(song_id):
    with open("failed_ids.txt", "a") as f:
        f.write(f"{song_id}\n")
        
# 获取最后一个上传的异常 id
def get_last_failed_id() -> Union[int, None]:
    if not os.path.exists("failed_ids.txt"):
        return None
    with open("failed_ids.txt", "r") as f:
        ids = [line.strip() for line in f]
    return int(ids[-1])

# 处理歌曲导入请求
def process_songs(song_info_list, cookie):
    failed_attempts = {}  # 记录每个 ID 失败的次数
    for song_info in song_info_list:
        song_id = song_info['id']
        print(f"正在导入歌曲ID: {song_id}")

        # 已上传则跳过
        if has_uploaded(song_id, cookie):
            print('该歌曲已上传，跳过！')
            continue
            
        # 查询歌曲的详细信息
        song_details = get_song_details([song_id])
        if song_details:
            song_name = song_details[0]['name']
            song_artist = song_details[0]['ar'][0]['name']
            song_album = song_details[0]['al']['name']
            print(f"歌曲名: {song_name}, 演唱者: {song_artist}, 专辑: {song_album}")
            # 更新 song_info 添加 artist 和 album 信息
            song_info['artist'] = song_artist
            song_info['album'] = song_album
        try:
            try_to_upload_song(song_info, cookie)
        except Exception as e:
            print(f'上传过程异常，跳过该歌曲：{e}')
            save_failed_id(song_id)

def try_to_upload_song(song_info, cookie):
    song_id = song_info['id']
    attempts = 0
    while attempts < 3:
        result = import_song(song_info, cookie)
        
        if result:
            success_songs = result.get('data', {}).get('successSongs', [])
            failed = result.get('data', {}).get('failed', [])
            
            if success_songs:
                print(f"歌曲 {song_id} 导入成功！")
                break  # 成功则跳出循环
            else:
                print(f"歌曲 {song_id} 导入失败，失败原因：{failed}")
                if all(f['code'] == -100 for f in failed):  # 文件已存在的错误码
                    print(f"歌曲 {song_id} 文件已存在，跳过")
                    save_failed_id(song_id)  # 保存失败的 ID
                    break
        time.sleep(5)  # 请求失败后等待 5 秒重新请求
        attempts += 1
    
    if attempts == 3:  # 如果失败三次，则跳过此 ID
        print(f"歌曲 {song_id} 失败三次，跳过该歌曲。")
        save_failed_id(song_id)  # 保存失败的 ID
        
def get_resume_song_info_list(song_info_list) -> list:
    last_failed_id = get_last_failed_id()
    if last_failed_id is None:
        print("暂无上传失败记录，从头开始上传")
        return song_info_list
    for index, song_info in enumerate(song_info_list):
        if int(song_info['id']) == last_failed_id:
            print(f"当前已上传: {index + 1}，最后上传失败的 id: {song_info['id']}")
            return song_info_list[index + 1:]
    print('暂未匹配到最后一次失败的 song_id, 将从头开始上传')
    return song_info_list

# 主函数
def main():
    # 尝试读取已保存的 cookie
    cookie = read_cookie()
    
    if cookie:
        #print(f"读取到已保存的 cookie: {cookie}")
        # 获取并显示云盘信息
        get_cloud_info(cookie)
    else:
        print("没有找到 cookie，正在执行登录...")
        # 执行 login 函数获取新 cookie
        cookie = login()
        if cookie:
            print(f"登录成功，cookie: {cookie}")
            # 获取并显示云盘信息
            get_cloud_info(cookie)
        else:
            print("登录失败")
            return

    # 读取歌曲数据
    songs_data = read_songs_data()
    
    if songs_data:
        #print(f"共找到 {len(songs_data)} 首歌曲，提取歌曲 ID 和其他信息...")
        song_info_list = get_all_song_info(songs_data)
        #print(f"所有歌曲信息: {song_info_list}")
        
        # 从上次失败的歌曲开始上传
        song_info_list = get_resume_song_info_list(song_info_list)
        
        # 执行歌曲导入请求
        process_songs(song_info_list, cookie)
    else:
        print("没有找到任何歌曲数据")

if __name__ == "__main__":
    main()
