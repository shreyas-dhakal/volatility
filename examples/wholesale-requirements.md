# Wholesale ERP - synthetic demonstration requirements

This fictional example is for learning Galvanise. It is not a connected repository or live AI finding.

Supplier onboarding: new suppliers use different protocols and field mappings. The internal purchasing workflow should stay stable. We anticipate onboarding more suppliers next year; we do not yet know whether approval rules vary per supplier.

Inventory: expansion to five warehouses next year will require warehouse-specific allocation policies. Existing order-processing rules rarely change. Ask operations who owns allocation exceptions.

Purchasing: central buyers approve purchases through the existing workflow. Customer-specific pricing may change with negotiated contracts. Ask sales who approves price exceptions and how often the pricing rules change.

Source-level calls in the companion synthetic graph demonstrate relationships only. They do not prove runtime writes, business ownership, test coverage or maintenance savings.
