from datetime import datetime

class FiringRequest:
    def __init__(self, discord_id, full_name, rank, reason="псж", photo_link=None, recovery_option="без возможности восстановления"):
        self.discord_id = discord_id
        self.full_name = full_name
        self.rank = rank
        self.reason = reason
        self.photo_link = photo_link
        self.recovery_option = recovery_option
        self.created_at = datetime.now()
        self.status = "pending"
        self.message_link = None

    def to_dict(self):
        return {
            'discord_id': self.discord_id,
            'full_name': self.full_name,
            'rank': self.rank,
            'reason': self.reason,
            'photo_link': self.photo_link,
            'recovery_option': self.recovery_option,
            'created_at': self.created_at.isoformat(),
            'status': self.status,
            'message_link': self.message_link
        }

class PromotionRequest:
    def __init__(self, discord_id, full_name, new_rank, message_link=None):
        self.discord_id = discord_id
        self.full_name = full_name
        self.new_rank = new_rank
        self.message_link = message_link
        self.created_at = datetime.now()
        self.status = "pending"

    def to_dict(self):
        return {
            'discord_id': self.discord_id,
            'full_name': self.full_name,
            'new_rank': self.new_rank,
            'message_link': self.message_link,
            'created_at': self.created_at.isoformat(),
            'status': self.status
        }