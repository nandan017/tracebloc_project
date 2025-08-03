// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract TraceBlocLedger {

    struct Update {
        uint256 timestamp;
        string productId; // Using string for UUID
        string stage;
        string location;
    }

    Update[] public updates;

    event StepAdded(
        uint256 indexed updateId,
        uint256 timestamp,
        string productId,
        string stage
    );

    function addUpdate(
        string memory _productId,
        string memory _stage,
        string memory _location
    ) public {
        uint256 updateId = updates.length;
        updates.push(Update({
            timestamp: block.timestamp,
            productId: _productId,
            stage: _stage,
            location: _location
        }));
        emit StepAdded(updateId, block.timestamp, _productId, _stage);
    }
}