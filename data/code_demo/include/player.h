#pragma once
struct Player { int health; int item_count; };
extern Player players[100];
void SpawnPlayer(int id);
void SetPlayerHealth(int id, int health);
void ResetInventory(int id);
