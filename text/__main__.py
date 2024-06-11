from fastapi import FastAPI

from builder.command import create_command
from builder.router import TextView

app = FastAPI()
app.include_router(TextView.view_router)

if __name__ == "__main__":
    command = create_command()
