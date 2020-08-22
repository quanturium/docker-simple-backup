"""
Allow docker_simple_backup to be executable through `python -m docker_simple_backup`
"""
from docker_simple_backup.run import main

if __name__ == "__main__":
    main()
