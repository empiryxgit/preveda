# 0003 Federate only the final layer
Context: FRD budget is about 11 KB per night; full ResNet-18 is about 45 MB. Decision: share only the classifier head (2,052 floats, about 8 KB), backbone fixed per release. Consequence: fits the budget; backbone upgrades ship through the Model Registry.
