#include "player.h"

void SpawnPlayer(int id) {
    SetPlayerHealth(id, 100);
    ResetInventory(id);
}

void SetPlayerHealth(int id, int health) {
    players[id].health = health;
}

void ResetInventory(int id) {
    players[id].item_count = 0;
}
