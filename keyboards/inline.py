from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from typing import List, Dict

def get_reaction_keyboard(channel_id: int, message_id: int, reaction_types: List[str], counts: Dict[str, int]) -> InlineKeyboardMarkup:
    """
    Builds the inline reaction keyboard with live counts.
    Supported types:
    - Emojis (e.g., '👍', '🔥', '❤️')
    - Star ratings ('1', '2', '3', '4', '5' representing 1-5 Stars)
    """
    buttons = []
    
    # Check if this is a star rating setup
    is_star_rating = all(r.isdigit() and 1 <= int(r) <= 5 for r in reaction_types)
    
    for r_type in reaction_types:
        count = counts.get(r_type, 0)
        
        # Display label
        if is_star_rating:
            # Show "⭐ X (Count)"
            stars = "⭐" * int(r_type)
            label = f"{stars} ({count})"
        else:
            # Show "🔥 Count"
            label = f"{r_type} {count}"
            
        callback_data = f"react:{channel_id}:{message_id}:{r_type}"
        buttons.append(InlineKeyboardButton(text=label, callback_data=callback_data))
        
    # Group buttons
    keyboard = []
    if is_star_rating:
        # Star ratings stacked vertically/in rows
        for btn in buttons:
            keyboard.append([btn])
    else:
        # Emoji reactions side-by-side
        keyboard.append(buttons)
        
    return InlineKeyboardMarkup(inline_keyboard=keyboard)
