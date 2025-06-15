import os
from dotenv import load_dotenv
from crewai import Crew, Task
from agents.search_agent import search_agent

# Load environment variables from .env
load_dotenv()

# Define the task for the search agent
funding_task = Task(
    description=(
        "Search for at least 5 active or upcoming development funding opportunities "
        "for documentary, fiction, or hybrid audiovisual projects. "
        "Include public grants, international co-productions, or lab programs. "
        "For each, provide: name, deadline, eligible regions, and website link."
    ),
    expected_output=(
        "A list of at least 5 funding opportunities with: "
        "1) Name, 2) Deadline, 3) Eligible regions/countries, 4) Website link."
    ),
    agent=search_agent
)

# Assemble the Crew
crew = Crew(
    agents=[search_agent],
    tasks=[funding_task],
    verbose=True
)

# Run the Crew
if __name__ == "__main__":
    result = crew.kickoff()
    print("\nFinal Output:\n")
    print(result)

