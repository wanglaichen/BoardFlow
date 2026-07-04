def find_card_on_board(board_service, board_id: str, card_id: str) -> dict | None:
    detail = board_service.get_board_detail(board_id)
    for lst in detail.get("lists", []):
        for item in lst.get("cards", []):
            if str(item.get("id")) == str(card_id):
                return item
    return None
