from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

class NGSILDSubscriptionPayload(BaseModel):
    id: str
    type: str = "Notification"
    subscriptionId: str
    notifiedAt: str
    data: List[Dict[str, Any]]
