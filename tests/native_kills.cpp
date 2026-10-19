#include "../src/kill_ledger.h"
#include "../src/actors_protocol.h"
int main() {
    sa_agent::actors::KillLedger ledger;
    if (ledger.Register(257, false)) return 1;
    if (!ledger.Register(257, true) || ledger.Register(257, true)) return 2;
    // Recycled pool slot with a new generation represents a different NPC.
    ledger.Observe(258);
    if (!ledger.Register(258, true) || ledger.Register(258, true)) return 3;
    if (ledger.Register(-1, true) || ledger.Register(0x7fffffff, true)) return 4;
    // Reuse through a complete generation wrap is observed as another lifetime.
    ledger.Observe(257);
    if (!ledger.Register(257, true)) return 5;
    ledger.Reset();
    if (!ledger.Register(257, true) || ledger.Register(257, true)) return 6;
    return 0;
}
