# Copyright 2026 Google LLC
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     https://www.apache.org/licenses/LICENSE-2.0

import re
import logging
from google.adk.plugins.base_plugin import BasePlugin
from google.adk.agents.callback_context import CallbackContext
from google.adk.models.llm_request import LlmRequest
from google.adk.events import Event

logger = logging.getLogger("security")

# PII Regex patterns
EMAIL_REGEX = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]*[a-zA-Z0-9-]")
PHONE_REGEX = re.compile(r"\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b")
SSN_REGEX = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")

# Input Validation Regex (prevent prompt injection, script injection, basic HTML tags)
DANGEROUS_PATTERNS = [
    re.compile(r"<script.*?>.*?</script>", re.IGNORECASE | re.DOTALL),
    re.compile(r"javascript:", re.IGNORECASE),
    re.compile(r"onload=", re.IGNORECASE),
    re.compile(r"onerror=", re.IGNORECASE),
    # Common prompt injection signals
    re.compile(r"\bignore\b.*\bprevious\b.*\binstructions\b", re.IGNORECASE),
    re.compile(r"\bsystem\b.*\bprompt\b", re.IGNORECASE)
]

def mask_text(text: str) -> str:
    """Masks sensitive personal information (emails, phone numbers, SSNs) in text."""
    if not isinstance(text, str):
        return text
    text = EMAIL_REGEX.sub("[EMAIL_MASKED]", text)
    text = PHONE_REGEX.sub("[PHONE_MASKED]", text)
    text = SSN_REGEX.sub("[SSN_MASKED]", text)
    return text

def validate_user_input(text: str) -> bool:
    """Validates user input against common injection and scripting attacks.
    
    Returns True if safe, False if unsafe.
    """
    if not text or not isinstance(text, str):
        return False
        
    for pattern in DANGEROUS_PATTERNS:
        if pattern.search(text):
            logger.warning(f"Input validation failed for text: {text[:50]}... due to pattern: {pattern.pattern}")
            return False
            
    return True

class PIIMaskingPlugin(BasePlugin):
    """ADK plugin to dynamically mask PII in model requests and execution events."""
    
    def __init__(self, name: str = "pii_masking"):
        super().__init__(name=name)
        
    async def before_model_callback(self, *, llm_request: LlmRequest = None, **kwargs):
        """Masks PII in contents before sending them to the LLM."""
        if not llm_request or not llm_request.contents:
            return None
            
        for content in llm_request.contents:
            if hasattr(content, "parts") and content.parts:
                for part in content.parts:
                    if hasattr(part, "text") and part.text:
                        part.text = mask_text(part.text)
                        
        return None  # Continue with execution

    async def on_event_callback(self, *, event: Event = None, **kwargs):
        """Masks PII in events emitted during runner execution (such as tool calls or outputs)."""
        if not event:
            return None
            
        # Mask text in the event content
        if hasattr(event, "content") and event.content:
            if hasattr(event.content, "parts") and event.content.parts:
                for part in event.content.parts:
                    if hasattr(part, "text") and part.text:
                        part.text = mask_text(part.text)
                        
        # Mask text in the event output (e.g. tool results)
        if hasattr(event, "output") and isinstance(event.output, dict):
            for k, v in event.output.items():
                if isinstance(v, str):
                    event.output[k] = mask_text(v)
                elif isinstance(v, dict):
                    # Mask deep dict values
                    for sub_k, sub_v in v.items():
                        if isinstance(sub_v, str):
                            v[sub_k] = mask_text(sub_v)
                            
        return None
