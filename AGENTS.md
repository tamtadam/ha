# Coding conventions

- Pass function, method, and constructor arguments by keyword whenever the callable's signature permits it. Use positional arguments only for positional-only parameters or APIs that explicitly require positional arguments. Avoid multiple unnamed arguments because their meaning is hard to read at the call site.