# -*- coding: utf-8 -*-
from pathlib import Path
import json
import requests
import wave
import pyaudio
import re
import alkana

CHUNK_SIZE = 1024
BASE_URL = "http://127.0.0.1:50021"

def alkana_(text:str) -> str:
    
    pattern = r'[a-zA-Z]+'
    words = re.findall(pattern, text)
    
    for w in words:
        kana = alkana.get_kana(w)
        if kana:
            text = re.sub(w, kana, text)

    return text

def text2voice(
    text:str, 
    filename:str, 
    path:Path, 
    speaker:int=0, 
    volume:float=1.0, 
    speed:float=1.0, 
    pitch:float=0.0, 
    intonation:float=1.0,
    post:float=0.0
) -> Path:

    path = path.resolve()
    path.mkdir(parents=True, exist_ok=True)

    text = alkana_(text)

    # audio_query
    try:
        res1 = requests.post(BASE_URL + "/audio_query",
                        params={"text": text, "speaker": speaker})
        res1.raise_for_status()
    except Exception as e:
        #print("Error :", e)
        return
    
    res1 = res1.json()
    res1["volumeScale"]=volume
    res1["speedScale"]=speed
    res1["pitchScale"]=pitch
    res1["intonationScale"]=intonation
    res1["postPhonemeLength"]=post
    
    # synthesis
    res2 = requests.post(BASE_URL + "/synthesis",
                        params={"speaker": speaker},
                        data=json.dumps(res1))
    
    audio_file = Path(path, filename + '.wav')
    with open(audio_file, mode="wb") as f:
        f.write(res2.content)
    
    return audio_file

def play_wave(wav:Path, delete=False):
    
    with wave.open(str(wav), mode='r') as wf:

        p = pyaudio.PyAudio()
        stream = p.open(format=p.get_format_from_width(wf.getsampwidth()),
                        channels=wf.getnchannels(),
                        rate=wf.getframerate(),
                        output=True)

        data = wf.readframes(CHUNK_SIZE)
        while data != b'':
            stream.write(data)
            data = wf.readframes(CHUNK_SIZE)

        stream.stop_stream()
        stream.close()
        p.terminate()

    if delete:
        wav.unlink()