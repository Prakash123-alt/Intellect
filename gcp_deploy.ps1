# One-click GCP deployment script
# Run this in PowerShell from d:\Student_prep\Intellect

$projectId = Read-Host "Enter your GCP Project ID"
$groqKey = Read-Host "Enter your Groq API Key" -AsSecureString
$secret = -join ((65..90) + (97..122) + (48..57) | Get-Random -Count 32 | ForEach-Object { [char]$_ })

# Update app.yaml with Groq key
$yaml = Get-Content "app.yaml" -Raw
$yaml = $yaml -replace '"your-groq-api-key-here"', '"' + (ConvertFrom-SecureString $groqKey -AsPlainText) + '"'
$yaml = $yaml -replace '"your-secret-key-here"', '"' + $secret + '"'
$yaml | Set-Content "app.yaml" -NoNewline

# Set project and deploy
gcloud config set project $projectId
gcloud app deploy --quiet

Write-Host "Deployment complete. Run 'gcloud app browse' to open your app."
