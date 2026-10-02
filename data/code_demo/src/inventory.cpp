#include "player.h"

int AddInventoryItem(int id) {
    return ++players[id].item_count;
}

bool HasItems(int id) {
    return players[id].item_count > 0;
}
