Refine this callee analysis using the following domain feedback, while keeping claims tied to the supplied implementation and marking proof gaps explicitly.

The intended logical model is richer than a map to raw frame addresses:
- each address space maps user pages to a logical page view containing a backing identity and permissions;
- backing contents live in a separate backing store;
- a backing may have mappings in other address spaces or a detached retained owner;
- removing the selected mapping removes the backing from the logical store only when no mapped or retained owner remains;
- allocator/resource conservation is a separate world-level observation from logical mapping equality.

For a valid user page under the common coherent-representation/readiness precondition, the target contract wants internal lookup and cleanup errors to be unreachable, not treated as ordinary allowed failures. For an invalid user address, the desired error is an unchanged-state invalid-range failure. However, the implementation contains syntactic fallible operations after mutation, especially directory cleanup, so retain a specific proof obligation to establish their unreachability and do not silently assume failure atomicity.

Revise the abstraction to separate:
1. per-space page mapping and page metadata;
2. backing identity, contents, and last-owner reclamation;
3. physical allocator/resource authority;
4. page-table representation and cleanup;
5. lifecycle/address-space identity.

Produce a caller-usable contract for `VirtMemoryManager::try_unmap_upage`, with a clear distinction between the intended total contract under readiness invariants and the weaker body-local contract that is currently justified.
