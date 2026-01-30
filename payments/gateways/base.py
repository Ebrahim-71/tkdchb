# payments/gateways/base.py
from abc import ABC, abstractmethod

class PaymentGatewayBase(ABC):
    name: str = "base"

    def __init__(self, config=None):
        self.config = config or {}

    @abstractmethod
    def initiate(self, intent) -> dict:
        """Create payment session.
        Return: {'redirect_url': str, 'token': str}"""
        raise NotImplementedError

    @abstractmethod
    def verify(self, request) -> dict:
        """Handle callback.
        Return: {'ok': bool, 'ref_id': str, 'card_pan': str}"""
        raise NotImplementedError
