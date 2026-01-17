from dataclasses import dataclass

@dataclass
class Message:
    user : str
    type : str
    text : str

    def __len__(self):
        return len(self.text) + len(self.type) + len(self.user)