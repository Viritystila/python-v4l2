v4l2 wrapper
=======================

A wrapper providing advanced functionality for v4l2 devices

-----------------------

The goal of this project is to provide a dynamic interface that can be used to a) develop advanced interfaces into a v4l2 device b) provide an extendable interface.

This is achieved via defining device wrapper classes. All device wrappers are under the _wrappers folder. Every wrapper performs a specific subset of v4l2 functionality. Generally, a wrapper class should inherit from a class that is based on 'v4l2_device_Base'. This ensures that the core v4l2 functionality is available to the derived class. It also assures core device initialization and provides a uniform interface to device operations like ioctl's and device read/writes.

When a device wrapper is created, the device wrapper framework goes through every wrapper and initializes it. Every wrapper in it's init class performs initialization operations on the device. If any of the operations fails or is not available by the targetted device, it fails and the specific wrapper is removed from the list. This ensures that the final wrapper that will be created will only contain the functionality that is available for the target hardware.

Finally when all the compatible wrappers are determined a new wrapper is made that encapsulated all the available subsystems.

If a new wrapper should be made, use the template available under the templates folder
