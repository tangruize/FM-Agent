# Nanvix selected-page unmap intent

Analyze `VirtMemoryManager::try_unmap_upage` independently of existing formal specifications.

Candidate intent:
- if the selected valid user virtual page is mapped, remove exactly that abstract mapping and return `Ok(true)`;
- if it is not mapped, preserve the mapping relation and return `Ok(false)`;
- preserve every unrelated virtual mapping, active address-space identity, protected/kernel/shared mapping, and allocator identity;
- transfer or release authority for the removed backing user frame exactly once, including the implicit destructor of the returned frame;
- reclaim an empty lower-level page table only when its cleanup and ownership preconditions hold, without changing the abstract mapping result;
- on error, do not fabricate successful removal, and characterize whether partial concrete mutation is possible.

Derive an abstraction that separates at least:
1. the abstract user virtual-address-to-frame mapping relation;
2. page-table and page-directory representation;
3. backing-frame ownership/allocator authority;
4. page-table cleanup and reclamation state.

The caller is intentionally tiny, so identify the minimum contract required from `Vmem::unmap`. Suggest stronger and weaker variants with discriminating counterexamples. Do not inspect or rely on adjacent `.spec.rs` or `.proof.rs` files in this first pass.
