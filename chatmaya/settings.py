# -*- coding: utf-8 -*-
import json
from typing import Dict
from pydantic import BaseModel

from PySide2 import QtWidgets, QtCore

from .info import USER_SETTINGS_JSON

class CompletionSettings(BaseModel):
    temperature :float = 0.7
    top_p :float = 1.0
    presence_penalty :float = 0.0
    frequency_penalty :float = 0.0

class VoiceSettings(BaseModel):
    speakerid :int = 47
    speed :float = 1.1
    pitch :float = 0.0
    intonation :float = 1.0
    volume :float = 1.0
    post :float = 0.1

class SettingsData(BaseModel):
    completion :CompletionSettings = CompletionSettings()
    voice :VoiceSettings = VoiceSettings()

    @classmethod
    def from_dict(cls, dict:Dict):
        completion_settings = CompletionSettings(
            temperature = dict["completion"]["temperature"],
            top_p = dict["completion"]["top_p"],
            presence_penalty = dict["completion"]["presence_penalty"],
            frequency_penalty = dict["completion"]["frequency_penalty"],
        )
        voice_settings = VoiceSettings(
            speakerid = dict["voice"]["speakerid"],
            speed = dict["voice"]["speed"],
            pitch = dict["voice"]["pitch"],
            intonation = dict["voice"]["intonation"],
            volume = dict["voice"]["volume"],
            post = dict["voice"]["post"],
        )
        
        return cls(
            completion=completion_settings,
            voice=voice_settings
        )
    
    def to_dict(self) -> Dict:
        return {
            "completion": {
                "temperature": self.completion.temperature,
                "top_p": self.completion.top_p,
                "presence_penalty": self.completion.presence_penalty,
                "frequency_penalty": self.completion.frequency_penalty
            },
            "voice": {
                "speakerid": self.voice.speakerid,
                "speed": self.voice.speed,
                "pitch": self.voice.pitch,
                "intonation": self.voice.intonation,
                "volume": self.voice.volume,
                "post": self.voice.post
            }
        }

class Settings(object):

    def __init__(self):
        self.filepath = USER_SETTINGS_JSON
        
        self._data = self.__import_from_file()

        if self._data is None:
            self._data = SettingsData()

        self.__export_file()

    def get_settings(self, *args):
        return self._data
    
    def update(self, parent=None, *args):
        data, accepted = SettingsDialog.set(parent=parent, data=self._data)
        
        if not accepted:
            return

        self._data = data        
        self.__export_file()

    def __import_from_file(self, *args):
        if not self.filepath.is_file():
            return

        try:
            with open(self.filepath, 'r') as f:
                data = json.load(f)
            return SettingsData.from_dict(data)
        except:
            print("Settings could not be applied. Use default settings.")
            return

    def __export_file(self, *args):
        try:
            with open(self.filepath, 'w', encoding='utf-8') as f:
                json.dump(self._data.to_dict(), f, indent=4)
            return True
        except:
            return

class SettingsDialog(QtWidgets.QDialog):

    _data :SettingsData
    
    def __init__(self, parent=None, *args):
        super(SettingsDialog, self).__init__(parent, *args)
    
    def init_UI(self, *args):
        self.setWindowTitle('Settings')
        
        # Completion Settings group
        completion_group = QtWidgets.QGroupBox("ChatCompletion")
        completion_layout = QtWidgets.QFormLayout(completion_group)

        # temperature
        self.temperature_spinbox = QtWidgets.QDoubleSpinBox(self)
        self.temperature_spinbox.setRange(0.0, 2.0)
        self.temperature_spinbox.setSingleStep(0.1)
        self.temperature_spinbox.setMinimumWidth(100)
        completion_layout.addRow("Temperature:", self.temperature_spinbox)

        # top_p
        self.top_p_spinbox = QtWidgets.QDoubleSpinBox(self)
        self.top_p_spinbox.setRange(0.0, 2.0)
        self.top_p_spinbox.setSingleStep(0.1)
        self.top_p_spinbox.setMinimumWidth(100)
        completion_layout.addRow("Top P:", self.top_p_spinbox)

        # presence_penalty
        self.presence_penalty_spinbox = QtWidgets.QDoubleSpinBox(self)
        self.presence_penalty_spinbox.setRange(0.0, 2.0)
        self.presence_penalty_spinbox.setSingleStep(0.1)
        self.presence_penalty_spinbox.setMinimumWidth(100)
        completion_layout.addRow("Presence Penalty:", self.presence_penalty_spinbox)

        # frequency_penalty
        self.frequency_penalty_spinbox = QtWidgets.QDoubleSpinBox(self)
        self.frequency_penalty_spinbox.setRange(0.0, 2.0)
        self.frequency_penalty_spinbox.setSingleStep(0.1)
        self.frequency_penalty_spinbox.setMinimumWidth(100)
        completion_layout.addRow("Frequency Penalty:", self.frequency_penalty_spinbox)
        
        # Voice Settings group
        voice_group = QtWidgets.QGroupBox("VOICEVOX")
        voice_layout = QtWidgets.QFormLayout(voice_group)

        # speakerid
        self.speakerid_spinbox = QtWidgets.QSpinBox(self)
        self.speakerid_spinbox.setMinimumWidth(60)
        voice_layout.addRow("Speaker ID:", self.speakerid_spinbox)

        # speed
        self.speed_spinbox = QtWidgets.QDoubleSpinBox(self)
        self.speed_spinbox.setRange(0.5, 2.0)
        self.speed_spinbox.setSingleStep(0.1)
        self.speed_spinbox.setMinimumWidth(60)
        voice_layout.addRow("Speed:", self.speed_spinbox)

        # pitch
        self.pitch_spinbox = QtWidgets.QDoubleSpinBox(self)
        self.pitch_spinbox.setRange(-0.15, 0.15)
        self.pitch_spinbox.setSingleStep(0.01)
        self.pitch_spinbox.setMinimumWidth(60)
        voice_layout.addRow("Pitch:", self.pitch_spinbox)

        # intonation
        self.intonation_spinbox = QtWidgets.QDoubleSpinBox(self)
        self.intonation_spinbox.setRange(0.0, 2.0)
        self.intonation_spinbox.setSingleStep(0.1)
        self.intonation_spinbox.setMinimumWidth(60)
        voice_layout.addRow("Intonation:", self.intonation_spinbox)

        # volume
        self.volume_spinbox = QtWidgets.QDoubleSpinBox(self)
        self.volume_spinbox.setRange(0.0, 5.0)
        self.volume_spinbox.setSingleStep(0.1)
        self.volume_spinbox.setMinimumWidth(60)
        voice_layout.addRow("Volume:", self.volume_spinbox)

        # post
        self.post_spinbox = QtWidgets.QDoubleSpinBox(self)
        self.post_spinbox.setRange(0.0, 1.5)
        self.post_spinbox.setSingleStep(0.1)
        self.post_spinbox.setMinimumWidth(60)
        voice_layout.addRow("Post:", self.post_spinbox)

        # Buttons
        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel,
            QtCore.Qt.Horizontal,
            self
        )
        buttons.accepted.connect(self.save_and_accept)
        buttons.rejected.connect(self.reject)

        settings_layout = QtWidgets.QHBoxLayout()
        settings_layout.addWidget(completion_group)
        settings_layout.addWidget(voice_group)
        
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.addLayout(settings_layout)
        main_layout.addWidget(buttons)

    def set_UI_values(self, *args):
        try:
            self.temperature_spinbox.setValue(self._data.completion.temperature)
            self.top_p_spinbox.setValue(self._data.completion.top_p)
            self.presence_penalty_spinbox.setValue(self._data.completion.presence_penalty)
            self.frequency_penalty_spinbox.setValue(self._data.completion.frequency_penalty)

            self.speakerid_spinbox.setValue(self._data.voice.speakerid)
            self.speed_spinbox.setValue(self._data.voice.speed)
            self.pitch_spinbox.setValue(self._data.voice.pitch)
            self.intonation_spinbox.setValue(self._data.voice.intonation)
            self.volume_spinbox.setValue(self._data.voice.volume)
            self.post_spinbox.setValue(self._data.voice.post)
        except:
            pass
    
    def save_and_accept(self):
        self._data.completion.temperature = round(self.temperature_spinbox.value(), 2)
        self._data.completion.top_p = round(self.top_p_spinbox.value(), 2)
        self._data.completion.presence_penalty = round(self.presence_penalty_spinbox.value(), 2)
        self._data.completion.frequency_penalty = round(self.frequency_penalty_spinbox.value(), 2)
        self._data.voice.speakerid = self.speakerid_spinbox.value()
        self._data.voice.speed = round(self.speed_spinbox.value(), 2)
        self._data.voice.pitch = round(self.pitch_spinbox.value(), 2)
        self._data.voice.intonation = round(self.intonation_spinbox.value(), 2)
        self._data.voice.volume = round(self.volume_spinbox.value(), 2)
        self._data.voice.post = round(self.post_spinbox.value(), 2)

        self.accept() 
    
    @staticmethod
    def set(parent=None, data:SettingsData=None, *args):
        if data is None:
            return
        
        dialog = SettingsDialog(parent)
        dialog._data = data
        dialog.init_UI()
        dialog.set_UI_values()
        result = dialog.exec_()

        return (dialog._data, result == QtWidgets.QDialog.Accepted)
